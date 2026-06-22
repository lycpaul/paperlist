#!/usr/bin/env python3
"""Scrape a MICCAI open-access paper list into an ICRA/IROS-style CSV.

Each MICCAI edition publishes an accepted-paper list plus a per-paper detail
page carrying the abstract, topics, and (often) code/dataset links. The hosting
and HTML layout changed over the years, so the scraper selects a *site profile*
per year:

  * ``posts`` (2024, 2025, papers.miccai.org/miccai-<year>/)
      List page already carries the title, author chips and the open-access PDF
      link; the detail page adds topics, abstract, code and dataset.
  * ``conf`` (2022, 2023, conferences.miccai.org/<year>/papers/)
      List page carries only titles + detail links; authors and the paper
      (DOI/SharedIt) link come from the detail page.
  * ``flat`` (2021, miccai2021.org/openaccess/paperlinks/)
      A flat <a> list on a separate host with relative detail URLs; everything
      else comes from the detail page.

All editions share the same detail-page anchors (``abstract-id``, ``link-id``,
``code-id``, ``dataset-id``), so detail parsing is unified across profiles.

Output columns (mirrors the recent ICRA/IROS "with abstract" CSVs):
    Title, Authors, Topics, Abstract, Code, Dataset, PDF, Paper Page

For 2021-2023 there is no open-access PDF, so the "PDF" column holds the paper's
DOI (or SharedIt) link instead. Only the Python standard library is used.

Examples:
    python scripts/scrape_miccai.py                 # full 2025 scrape
    python scripts/scrape_miccai.py --year 2023     # a different edition
    python scripts/scrape_miccai.py --limit 10      # quick smoke test
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Per-year site configuration. Unknown years fall back to the modern ``posts``
# layout under papers.miccai.org.
SITES = {
    "2025": {"list_url": "https://papers.miccai.org/miccai-2025/", "profile": "posts"},
    "2024": {"list_url": "https://papers.miccai.org/miccai-2024/", "profile": "posts"},
    "2023": {"list_url": "https://conferences.miccai.org/2023/papers/", "profile": "conf"},
    "2022": {"list_url": "https://conferences.miccai.org/2022/papers/", "profile": "conf"},
    "2021": {
        "list_url": "https://miccai2021.org/openaccess/paperlinks/index.html",
        "profile": "flat",
    },
}

PAPER_ID_RE = re.compile(r"Paper(\d+)\.html")

# --- list-page patterns -----------------------------------------------------
# "posts" profile: one item per ``posts-list-item-name`` span.
POSTS_DETAIL_RE = re.compile(r'href="(/miccai-\d+/\d+-Paper\d+\.html)"')
POSTS_TITLE_RE = re.compile(r"<b>(.*?)</b>", re.DOTALL)
POSTS_PDF_RE = re.compile(r'href="(https://[^"]*?_paper\.pdf)"')
POSTS_AUTHOR_RE = re.compile(r'tags#[^"]*">(.*?)</a>', re.DOTALL)
# "conf"/"flat" profiles: plain anchors to ``...NNN-PaperID.html`` detail pages.
ANCHOR_RE = re.compile(
    r'<a\s+href="([^"]*?\d+-Paper\d+\.html)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE
)

# --- detail-page patterns (shared across years) -----------------------------
TOPIC_REGION_RE = re.compile(r"Paper Topic\(s\):.*?</h2>(.*?)<h1", re.DOTALL | re.IGNORECASE)
CATEGORY_RE = re.compile(r'href="[^"]*categories#[^"]*"[^>]*>(.*?)</a>', re.DOTALL)
# Author chips on the detail page (used when the list page lacked authors).
# Match the chip anchors by their ``tags#`` href -- the enclosing
# ``<div class="post-tags">`` also carries that class but wraps the heading.
DETAIL_AUTHOR_RE = re.compile(r'href="[^"]*tags#[^"]*"[^>]*>(.*?)</a>', re.DOTALL)
ABSTRACT_RE = re.compile(
    r'id="abstract-id"[^>]*>(.*?)<h1\s+id="link-id"', re.DOTALL | re.IGNORECASE
)
# "Link to paper" section: open-access PDF (2024/25) or DOI/SharedIt (2021-23).
LINK_SECTION_RE = re.compile(
    r'id="link-id"[^>]*>(.*?)<h1\s+id="code-id"', re.DOTALL | re.IGNORECASE
)
CODE_SECTION_RE = re.compile(
    r'id="code-id"[^>]*>(.*?)<h1\s+id="dataset-id"', re.DOTALL | re.IGNORECASE
)
# Dataset section ends at the next heading (bibtex in 2024/25) or rule (2021-23).
DATASET_SECTION_RE = re.compile(
    r'id="dataset-id"[^>]*>(.*?)(?:<h1|<hr)', re.DOTALL | re.IGNORECASE
)
HREF_RE = re.compile(r'href="([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def clean_text(raw: str) -> str:
    """Strip HTML tags, unescape entities, and collapse whitespace."""
    text = TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str, retries: int = 3, timeout: int = 30) -> str:
    """GET ``url`` as UTF-8 text, retrying transient failures with backoff."""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as err:
            last_err = err
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def unique(items) -> list[str]:
    """Order-preserving de-duplication of non-empty strings."""
    seen: dict[str, None] = {}
    for item in items:
        item = item.strip()
        if item:
            seen.setdefault(item, None)
    return list(seen)


def new_record(title: str, detail_url: str, authors=None, pdf_url="") -> dict:
    pid = PAPER_ID_RE.search(detail_url)
    return {
        "paper_id": pid.group(1) if pid else "",
        "title": title,
        "detail_url": detail_url,
        "authors": authors or [],
        "pdf_url": pdf_url,
    }


def discover_papers(html_text: str, cfg: dict) -> list[dict]:
    """Parse the list page into per-paper records according to the profile."""
    list_url = cfg["list_url"]
    papers: list[dict] = []

    if cfg["profile"] == "posts":
        # One paper per item span; title/authors/PDF are all on the list page.
        for chunk in html_text.split("posts-list-item-name")[1:]:
            detail = POSTS_DETAIL_RE.search(chunk)
            title = POSTS_TITLE_RE.search(chunk)
            if not detail or not title:
                continue
            pdf = POSTS_PDF_RE.search(chunk)
            papers.append(
                new_record(
                    title=clean_text(title.group(1)),
                    detail_url=urljoin(list_url, detail.group(1)),
                    authors=[clean_text(a) for a in POSTS_AUTHOR_RE.findall(chunk)],
                    pdf_url=pdf.group(1) if pdf else "",
                )
            )
        return papers

    # "conf" and "flat": plain anchors; authors/PDF come from the detail page.
    seen_urls: set[str] = set()
    for href, text in ANCHOR_RE.findall(html_text):
        detail_url = urljoin(list_url, href)
        if detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)
        papers.append(new_record(title=clean_text(text), detail_url=detail_url))
    return papers


def section_links(section_re: re.Pattern, html_text: str) -> list[str]:
    """Return order-preserving unique hrefs from a detail-page section."""
    m = section_re.search(html_text)
    return unique(HREF_RE.findall(m.group(1))) if m else []


def paper_link(html_text: str) -> str:
    """Best paper link: open-access PDF if present, else DOI, else first link."""
    links = section_links(LINK_SECTION_RE, html_text)
    for href in links:
        if href.lower().endswith(".pdf"):
            return href
    for href in links:
        if "doi.org" in href.lower():
            return href
    return links[0] if links else ""


def parse_detail_page(html_text: str) -> dict:
    """Extract topics, abstract, code, dataset, detail-page authors and link."""
    topic_region = TOPIC_REGION_RE.search(html_text)
    topics = (
        unique(clean_text(t) for t in CATEGORY_RE.findall(topic_region.group(1)))
        if topic_region
        else []
    )

    abstract = ""
    m = ABSTRACT_RE.search(html_text)
    if m:
        abstract = re.sub(r"^Abstract\s*", "", clean_text(m.group(1)))
    if not abstract:  # fallback: <meta name="description"> mirrors the abstract
        meta = re.search(
            r'<meta\s+name="description"\s+content="(.*?)"', html_text, re.DOTALL
        )
        if meta:
            abstract = re.sub(r"^Abstract\s*", "", clean_text(meta.group(1)))

    return {
        "topics": "; ".join(topics),
        "abstract": abstract,
        "code": ";".join(section_links(CODE_SECTION_RE, html_text)),
        "dataset": ";".join(section_links(DATASET_SECTION_RE, html_text)),
        "detail_authors": unique(
            clean_text(a) for a in DETAIL_AUTHOR_RE.findall(html_text)
        ),
        "paper_link": paper_link(html_text),
    }


def detail_cache_path(cache_dir: str, paper_id: str, detail_url: str) -> str:
    name = paper_id or re.sub(r"[^0-9A-Za-z]+", "_", detail_url)[-40:]
    return os.path.join(cache_dir, f"{name}.html")


def get_detail_html(paper: dict, cache_dir: str, delay: float) -> str:
    """Return detail-page HTML, reading the on-disk cache when available."""
    path = detail_cache_path(cache_dir, paper["paper_id"], paper["detail_url"])
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    html_text = fetch(paper["detail_url"])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    if delay:
        time.sleep(delay)
    return html_text


def enrich(paper: dict, cache_dir: str, delay: float) -> dict:
    try:
        detail = parse_detail_page(get_detail_html(paper, cache_dir, delay))
        paper["topics"] = detail["topics"]
        paper["abstract"] = detail["abstract"]
        paper["code"] = detail["code"]
        paper["dataset"] = detail["dataset"]
        # Fill author/PDF gaps for the layouts that omit them from the list page.
        if not paper["authors"]:
            paper["authors"] = detail["detail_authors"]
        if not paper["pdf_url"]:
            paper["pdf_url"] = detail["paper_link"]
    except Exception as err:  # keep going; report the gap in the CSV
        log(f"  ! {paper['paper_id'] or paper['detail_url']}: {err}")
        for key in ("topics", "abstract", "code", "dataset"):
            paper.setdefault(key, "")
    return paper


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", default="2025", help="MICCAI edition year (default 2025)")
    ap.add_argument("--out", help="output CSV path (default: MICCAI/MICCAI<year>_Paper_List_with_Abstract.csv)")
    ap.add_argument("--cache-dir", help="HTML cache dir (default: MICCAI/.cache/<year>)")
    ap.add_argument("--workers", type=int, default=6, help="concurrent detail-page fetches (default 6)")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to sleep after each network fetch")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N papers (0 = all)")
    args = ap.parse_args()

    cfg = SITES.get(
        args.year,
        {"list_url": f"https://papers.miccai.org/miccai-{args.year}/", "profile": "posts"},
    )
    out_path = args.out or os.path.join(
        repo_root, "MICCAI", f"MICCAI{args.year}_Paper_List_with_Abstract.csv"
    )
    cache_dir = args.cache_dir or os.path.join(repo_root, "MICCAI", ".cache", args.year)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    log(f"Fetching paper list ({cfg['profile']} layout): {cfg['list_url']}")
    papers = discover_papers(fetch(cfg["list_url"]), cfg)
    log(f"Parsed {len(papers)} papers from the list page.")
    if not papers:
        log("No papers parsed - the page structure may have changed.")
        return 1
    if args.limit:
        papers = papers[: args.limit]
        log(f"Limiting to first {len(papers)} papers.")

    log(f"Fetching detail pages with {args.workers} workers (cache: {cache_dir}) ...")
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(enrich, p, cache_dir, args.delay): p for p in papers}
        for fut in as_completed(futures):
            fut.result()
            done += 1
            if done % 50 == 0 or done == len(papers):
                log(f"  {done}/{len(papers)} detail pages done")

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["Title", "Authors", "Topics", "Abstract", "Code", "Dataset", "PDF", "Paper Page"]
        )
        for p in papers:
            writer.writerow(
                [
                    p["title"],
                    ";".join(p["authors"]),
                    p["topics"],
                    p["abstract"],
                    p["code"],
                    p["dataset"],
                    p["pdf_url"],
                    p["detail_url"],
                ]
            )

    n_abs = sum(1 for p in papers if p["abstract"])
    log(f"Wrote {len(papers)} papers to {out_path} ({n_abs} with abstracts).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
