#!/usr/bin/env python3
"""Scrape a MIDL accepted-paper list from OpenReview into a CSV.

MIDL (Medical Imaging with Deep Learning) publishes its accepted papers on
OpenReview. Each edition's accepted set is the collection of notes whose
``venueid`` is ``MIDL.io/<year>/Conference``; the ``venue`` field on each note
records the acceptance type (``MIDL <year> Oral`` / ``MIDL <year> Poster``), so
both orals and posters are captured.

OpenReview runs two API generations and MIDL straddles them:

  * 2023 lives on the **v1** API (``api.openreview.net``), where each content
    field is a plain value and the per-paper TL;DR / community-implementation
    links are stored as note content (``TL;DR``, ``community_implementations``).
  * 2024 onward live on the **v2** API (``api2.openreview.net``), where every
    content field is wrapped as ``{"value": ...}`` and the TL;DR key is spelled
    ``TLDR``. v2 notes do not carry a ``community_implementations`` field (the
    OpenReview UI fetches those from CatalyzeX client-side), so that column is
    populated only where the API exposes it.

Output columns:
    Title, Authors, Session, Keywords, TL;DR, Abstract,
    Community Implementations, PDF, Paper Page

``Session`` is the acceptance type (``Oral`` / ``Poster``). ``Community
Implementations`` is the CatalyzeX code-listing URL when available. Only the
Python standard library is used.

Examples:
    python scripts/scrape_midl.py                 # all years 2023-2026
    python scripts/scrape_midl.py --year 2024     # a single edition
    python scripts/scrape_midl.py --limit 5       # quick smoke test
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

OPENREVIEW = "https://openreview.net"

# Per-year API generation. 2023 predates the v2 migration; 2024+ are on v2.
SITES = {
    "2023": {"api": "https://api.openreview.net", "version": 1},
    "2024": {"api": "https://api2.openreview.net", "version": 2},
    "2025": {"api": "https://api2.openreview.net", "version": 2},
    "2026": {"api": "https://api2.openreview.net", "version": 2},
}

YEARS = ("2023", "2024", "2025", "2026")

# CatalyzeX markdown link: "...](https://www.catalyzex.com/.../code)".
CI_URL_RE = re.compile(r"\((https?://[^)]+)\)")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fetch_json(url: str, retries: int = 4, timeout: int = 60) -> dict:
    """GET ``url`` and parse the JSON body, retrying transient failures."""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def fetch_notes(cfg: dict, year: str) -> list[dict]:
    """Page through every accepted note for one MIDL edition."""
    notes: list[dict] = []
    offset = 0
    while True:
        url = (
            f"{cfg['api']}/notes?content.venueid=MIDL.io/{year}/Conference"
            f"&limit=1000&offset={offset}"
        )
        batch = fetch_json(url).get("notes", [])
        notes.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return notes


def cv(content: dict, key: str, version: int):
    """Read a content field, unwrapping the v2 ``{"value": ...}`` envelope."""
    raw = content.get(key)
    if version == 2 and isinstance(raw, dict):
        return raw.get("value")
    return raw


def as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value:
        return [str(value).strip()]
    return []


def session_from_venue(venue: str, year: str) -> str:
    """Reduce ``MIDL <year> Oral`` to ``Oral`` (fallback: the raw venue)."""
    if not venue:
        return ""
    cleaned = re.sub(rf"^MIDL\s*{year}\s*", "", venue).strip()
    return cleaned or venue


def community_impl_url(value) -> str:
    """Extract the CatalyzeX URL from the markdown ``community_implementations``."""
    if not value:
        return ""
    match = CI_URL_RE.search(str(value))
    return match.group(1) if match else ""


def pdf_url(value) -> str:
    """Absolutize an OpenReview PDF path (``/pdf/...`` -> full URL)."""
    if not value:
        return ""
    value = str(value).strip()
    if value.startswith("http"):
        return value
    return f"{OPENREVIEW}{value}"


def parse_note(note: dict, version: int, year: str) -> dict:
    content = note.get("content", {})
    # The TL;DR key differs across API generations.
    tldr = cv(content, "TL;DR", version) or cv(content, "TLDR", version)
    return {
        "title": (cv(content, "title", version) or "").strip(),
        "authors": as_list(cv(content, "authors", version)),
        "session": session_from_venue(cv(content, "venue", version) or "", year),
        "keywords": as_list(cv(content, "keywords", version)),
        "tldr": (tldr or "").strip(),
        "abstract": (cv(content, "abstract", version) or "").strip(),
        "community": community_impl_url(cv(content, "community_implementations", version)),
        "pdf": pdf_url(cv(content, "pdf", version)),
        "forum": f"{OPENREVIEW}/forum?id={note.get('forum', note.get('id', ''))}",
    }


def get_notes_cached(cfg: dict, year: str, cache_dir: str) -> list[dict]:
    """Return raw notes for ``year``, reading the on-disk JSON cache if present."""
    path = os.path.join(cache_dir, f"{year}.json")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    notes = fetch_notes(cfg, year)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(notes, fh)
    return notes


# Orals first, then posters, then anything else; titles break ties.
_SESSION_RANK = {"Oral": 0, "Poster": 1}


def scrape_year(year: str, repo_root: str, cache_dir: str, limit: int) -> int:
    cfg = SITES[year]
    log(f"Fetching MIDL {year} (OpenReview API v{cfg['version']}) ...")
    notes = get_notes_cached(cfg, year, cache_dir)
    papers = [parse_note(n, cfg["version"], year) for n in notes]
    papers = [p for p in papers if p["title"]]
    papers.sort(key=lambda p: (_SESSION_RANK.get(p["session"], 9), p["title"].lower()))
    if not papers:
        log(f"  No accepted papers found for MIDL {year}.")
        return 0
    if limit:
        papers = papers[:limit]

    out_path = os.path.join(
        repo_root, "MIDL", f"MIDL{year}_Paper_List_with_Abstract.csv"
    )
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["Title", "Authors", "Session", "Keywords", "TL;DR", "Abstract",
             "Community Implementations", "PDF", "Paper Page"]
        )
        for p in papers:
            writer.writerow([
                p["title"],
                ";".join(p["authors"]),
                p["session"],
                ";".join(p["keywords"]),
                p["tldr"],
                p["abstract"],
                p["community"],
                p["pdf"],
                p["forum"],
            ])

    orals = sum(1 for p in papers if p["session"] == "Oral")
    posters = sum(1 for p in papers if p["session"] == "Poster")
    n_tldr = sum(1 for p in papers if p["tldr"])
    n_ci = sum(1 for p in papers if p["community"])
    log(
        f"  Wrote {len(papers)} papers to {out_path} "
        f"({orals} oral, {posters} poster, {n_tldr} TL;DR, {n_ci} community impl)."
    )
    return len(papers)


def main() -> int:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", help="single MIDL edition (default: all 2023-2026)")
    ap.add_argument("--cache-dir", help="raw-JSON cache dir (default: MIDL/.cache)")
    ap.add_argument("--limit", type=int, default=0,
                    help="only write the first N papers per year (0 = all)")
    args = ap.parse_args()

    years = [args.year] if args.year else list(YEARS)
    for y in years:
        if y not in SITES:
            log(f"Unknown MIDL year: {y} (known: {', '.join(YEARS)})")
            return 2

    cache_dir = args.cache_dir or os.path.join(repo_root, "MIDL", ".cache")
    os.makedirs(os.path.join(repo_root, "MIDL"), exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    total = 0
    for y in years:
        total += scrape_year(y, repo_root, cache_dir, args.limit)
    log(f"Done. {total} papers across {len(years)} edition(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
