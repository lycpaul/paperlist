#!/usr/bin/env python3
"""Scrape the MICCAI open-access paper list into an ICRA/IROS-style CSV.

The MICCAI proceedings site (https://papers.miccai.org/miccai-<year>/) renders a
single "List of Papers" page from which we get each paper's title, authors, and a
link to a per-paper detail page. The detail page additionally carries the paper's
topic categories and full abstract.

This script:
  1. downloads the list page and parses one record per paper,
  2. downloads each paper's detail page (cached on disk, so reruns are cheap and
     interrupted runs resume), and
  3. writes ``MICCAI<year>_Paper_List_with_Abstract.csv`` under the MICCAI folder.

Output columns (mirrors the recent ICRA/IROS "with abstract" CSVs):
    Title, Authors, Topics, Abstract, Code, Dataset, PDF, Paper Page

Only the Python standard library is used, so no ``pip install`` is required.

Examples:
    python scripts/scrape_miccai.py                 # full 2025 scrape
    python scripts/scrape_miccai.py --limit 10      # quick smoke test
    python scripts/scrape_miccai.py --year 2024     # a different edition
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
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (compatible; paperlist-scraper/1.0; "
    "+https://github.com/) Python-urllib"
)

# Per-paper record parsed from the list page.
DETAIL_HREF_RE = re.compile(r'href="(/miccai-\d+/\d+-Paper\d+\.html)"')
PDF_HREF_RE = re.compile(r'href="(https://papers\.miccai\.org/[^"]*?_paper\.pdf)"')
TITLE_RE = re.compile(r"<b>(.*?)</b>", re.DOTALL)
AUTHOR_RE = re.compile(r'tags#[^"]*">(.*?)</a>', re.DOTALL)
PAPER_ID_RE = re.compile(r"Paper(\d+)\.html")

# Detail-page fields.
ABSTRACT_RE = re.compile(
    r'id="abstract-id"[^>]*>(.*?)<h1\s+id="link-id"', re.DOTALL | re.IGNORECASE
)
# Topic categories link to ``categories#...``; author chips reuse the same
# ``post-category`` class but link to ``tags#...``, so match the href explicitly.
TOPIC_RE = re.compile(
    r'href="/miccai-\d+/categories#[^"]*"\s+class="post-category"[^>]*>(.*?)</a>',
    re.DOTALL,
)
# Code repository and dataset links live in their own ``<h1 id=...>`` sections;
# absent links render as plain "N/A" text (no href), so href extraction yields "".
CODE_SECTION_RE = re.compile(
    r'id="code-id"[^>]*>(.*?)<h1\s+id="dataset-id"', re.DOTALL | re.IGNORECASE
)
DATASET_SECTION_RE = re.compile(
    r'id="dataset-id"[^>]*>(.*?)<h1\s+id="bibtex-id"', re.DOTALL | re.IGNORECASE
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


def parse_list_page(html_text: str, base: str) -> list[dict]:
    """Return one record dict per paper found on the list page.

    Each record has: paper_id, title, authors (list), detail_url, pdf_url.
    The list is chunked on the per-item span class so titles/authors/links from
    different papers never bleed together.
    """
    chunks = html_text.split("posts-list-item-name")
    papers: list[dict] = []
    for chunk in chunks[1:]:  # chunk[0] is the page head, before the first paper
        detail = DETAIL_HREF_RE.search(chunk)
        title = TITLE_RE.search(chunk)
        if not detail or not title:
            continue
        detail_path = detail.group(1)
        pid_match = PAPER_ID_RE.search(detail_path)
        pdf = PDF_HREF_RE.search(chunk)
        papers.append(
            {
                "paper_id": pid_match.group(1) if pid_match else "",
                "title": clean_text(title.group(1)),
                "authors": [clean_text(a) for a in AUTHOR_RE.findall(chunk)],
                "detail_url": base.rstrip("/").rsplit("/", 1)[0] + detail_path,
                "pdf_url": pdf.group(1) if pdf else "",
            }
        )
    return papers


def section_links(section_re: re.Pattern, html_text: str) -> str:
    """Return ``;``-joined, order-preserving unique hrefs from a detail section."""
    m = section_re.search(html_text)
    if not m:
        return ""
    seen: dict[str, None] = {}
    for href in HREF_RE.findall(m.group(1)):
        seen.setdefault(href.strip(), None)
    return ";".join(seen)


def parse_detail_page(html_text: str) -> tuple[str, str, str, str]:
    """Return (topics, abstract, code, dataset) from a paper detail page."""
    # The detail page renders the topic block more than once; dedupe in order.
    seen: dict[str, None] = {}
    for t in TOPIC_RE.findall(html_text):
        seen.setdefault(clean_text(t), None)
    topics = "; ".join(seen)

    abstract = ""
    m = ABSTRACT_RE.search(html_text)
    if m:
        abstract = clean_text(m.group(1))
        # The section starts with the literal heading word "Abstract".
        abstract = re.sub(r"^Abstract\s*", "", abstract)
    if not abstract:
        # Fallback: the <meta name="description"> mirrors the abstract.
        meta = re.search(
            r'<meta\s+name="description"\s+content="(.*?)"', html_text, re.DOTALL
        )
        if meta:
            abstract = re.sub(r"^Abstract\s*", "", clean_text(meta.group(1)))

    code = section_links(CODE_SECTION_RE, html_text)
    dataset = section_links(DATASET_SECTION_RE, html_text)
    return topics, abstract, code, dataset


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
        html_text = get_detail_html(paper, cache_dir, delay)
        topics, abstract, code, dataset = parse_detail_page(html_text)
        paper["topics"] = topics
        paper["abstract"] = abstract
        paper["code"] = code
        paper["dataset"] = dataset
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

    base = f"https://papers.miccai.org/miccai-{args.year}/"
    out_path = args.out or os.path.join(
        repo_root, "MICCAI", f"MICCAI{args.year}_Paper_List_with_Abstract.csv"
    )
    cache_dir = args.cache_dir or os.path.join(repo_root, "MICCAI", ".cache", args.year)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    log(f"Fetching paper list: {base}")
    papers = parse_list_page(fetch(base), base)
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
