# Paper List Search Web App — Design

**Date:** 2026-06-22
**Status:** Approved

## Goal

A local web application to search and filter the repository's accepted-paper
lists. A user can keyword-search titles/abstracts, filter by conference and
year, filter by keyword/session/topic, and follow PDF/code/dataset links — all
from a single local web page backed by a small server that digests the CSV
files.

## Data Source

12 `_with_Abstract.csv` files across three conference directories
(`ICRA/`, `IROS/`, `MICCAI/`), ~18,651 papers total. Schemas are heterogeneous
(see root `README.md` "CSV file structure" section): column order differs by
file, some files have no header row, and 2025/IROS files prefix cell values with
the literal text `Keywords: ` and `Abstract: `.

## Architecture

A Flask app loads all 12 CSVs into memory once at startup, normalizing each
file's schema into one unified record shape, then serves a JSON search API to a
single-page vanilla-JS frontend (served as static files by the same Flask app).

```
paperlist/
├── webapp/
│   ├── app.py            # Flask app: routes + startup CSV load
│   ├── loader.py         # CSV -> normalized records (per-file schema handling)
│   ├── search.py         # filter/search/paginate over in-memory records
│   ├── static/
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   ├── tests/
│   │   ├── test_loader.py
│   │   └── test_search.py
│   └── requirements.txt  # flask
```

## Components

### `loader.py` — schema normalization (the one fiddly module)

Holds a per-file mapping table derived from the README schema matrix. For each
file it knows: column order, whether a header row is present, and which columns
map to which normalized field. It strips the literal `Keywords: ` / `Abstract: `
prefixes where present, and parses conference + year from the filename
(`<CONF><YEAR>_Paper_List_with_Abstract.csv`).

Files are parsed with Python's `csv` reader (not line splitting) because
abstracts and multi-author cells span multiple physical lines.

**Normalized record:**

```python
{
  "conference": str,        # "ICRA" | "IROS" | "MICCAI"
  "year": int,              # e.g. 2025
  "title": str,
  "authors": str,
  "session": str,           # session / topics, where present (else "")
  "keywords": str,          # keywords, prefix-stripped, where present (else "")
  "abstract": str,
  "affiliation": str,       # where present (else "")
  "links": {                # MICCAI mainly; "" where absent
    "pdf": str,
    "code": str,
    "dataset": str,
    "paper_page": str
  }
}
```

Per-file column layout (from README):

| File | Header | Columns (in order) |
| --- | --- | --- |
| ICRA2023 | yes | Title, Authors, Organisation, Session, Abstract |
| ICRA2024 | no  | Title, Authors, Affiliation, Session, Abstract |
| ICRA2025 | yes | Session, Paper Title, Author List, Keywords, Abstract |
| ICRA2026 | yes | Session, Paper Title, Author List, Affiliation, Keywords, Abstract |
| IROS2023 | no  | Title, Authors (with affiliation), Keywords, Abstract |
| IROS2024 | no  | Title, Authors, (Keywords), (Abstract) |
| IROS2025 | yes | Session, Paper Title, Author List, Keywords, Abstract |
| MICCAI2021-2025 | yes | Title, Authors, Topics, Abstract, Code, Dataset, PDF, Paper Page |

For MICCAI, `Topics` maps to `session`. `Keywords:`/`Abstract:` prefix stripping
applies to ICRA2025/2026, IROS2025, and IROS2023 keyword/abstract cells where
the prefix appears.

### `search.py` — query over in-memory records

Pure functions over the loaded record list:

- keyword `q`: case-insensitive substring match across `title` + `abstract` +
  `keywords`.
- `conference`, `year`: exact-match filters, multi-value (OR within a field,
  AND across fields).
- `keyword` filter: case-insensitive substring against `keywords` + `session`.
- pagination: `page` (1-based) and `page_size` (default 50), returns the slice
  plus the total match count.

### `app.py` — Flask routes

- `GET /` -> serves `static/index.html`.
- `GET /api/facets` -> `{conferences: [...], years: [...]}` distinct sorted
  values, to populate dropdowns.
- `GET /api/search?q=&conference=&year=&keyword=&page=&page_size=` ->
  `{total, page, page_size, results: [...]}`.

CSVs are loaded once at startup into a module-level list.

### Frontend (`static/`)

Single `index.html` with: a keyword search box, conference and year dropdowns
(multi-select), a keyword/session text filter, and a paginated results table.
Each row shows title, authors, conference/year, session/keywords, and a links
cell (PDF/code/dataset/paper-page where present). Clicking a row expands to show
the full abstract. Prev/Next controls and an "X results" counter. Vanilla JS,
no build step.

## Error Handling

- Loader skips malformed rows with a logged warning; reports skipped-row count
  per file at startup.
- Missing CSV files are logged but do not crash startup.
- The search API returns empty result sets (200) for no matches, never 500.
- Out-of-range `page` returns an empty `results` list with the correct `total`.

## Testing

- `test_loader.py`: one representative row per schema variant -> asserts correct
  field normalization, `Keywords:`/`Abstract:` prefix stripping, headerless-file
  handling, and filename -> conference/year parsing.
- `test_search.py`: keyword match (case-insensitivity, title vs abstract vs
  keywords), single and combined filters, multi-value filters, and pagination
  boundaries (first page, last partial page, out-of-range page).

## Non-Goals (YAGNI)

- No database, no persistence layer — in-memory load is sufficient for ~18k
  rows.
- No ranking/relevance scoring — substring match is enough for v1.
- No authentication, no write/edit of paper data.
- No build tooling for the frontend.
