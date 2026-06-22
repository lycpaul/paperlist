# Medical Robotics Paperlist

A collection of accepted-paper lists for the **ICRA** and **IROS** robotics
conferences and the **MICCAI** medical-imaging conference. For each conference
and year there are up to two files:

- a **`.md`** file — a Markdown table meant for quick browsing on GitHub, and
- a **`_with_Abstract.csv`** file — the full record including each paper's
  abstract (and, depending on the year, keywords / affiliations).

Data is sourced from the official conference program webpages. Much of it
originates from [Dong Li](https://github.com/DoongLi)'s paper-list repos. See
each conference subdirectory's `README.md` for the per-year sources and credits.

## Coverage

| Conference | Field | Years | Lists | Papers | Files |
| --- | --- | --- | --- | --- | --- |
| [ICRA](ICRA/README.md) | Robotics | 2023 – 2026 | 4 | 8,968 | `.md` + `.csv` |
| [IROS](IROS/README.md) | Robotics | 2023 – 2025 | 3 | 5,966 | `.md` + `.csv` |
| [MICCAI](MICCAI/README.md) | Medical imaging | 2021 – 2025 | 5 | 3,717 | `.csv` only |
| **Total** | | | **12** | **18,651** | |

Per-year paper counts and topic/session breakdowns live in each conference's
own `README.md`. Counts are taken from the canonical `.md` lists for ICRA/IROS
and from the generated CSVs for MICCAI (and for ICRA 2025, whose `.md` currently
duplicates the IROS 2025 list).

## Repository layout

```
paperlist/
├── ICRA/
│   ├── README.md
│   ├── ICRA2023_Paper_List.md
│   ├── ICRA2023_Paper_List_with_Abstract.csv
│   ├── ICRA2024_Paper_List.md
│   ├── ICRA2024_Paper_List_with_Abstract.csv
│   ├── ICRA2025_Paper_List.md
│   ├── ICRA2025_Paper_List_with_Abstract.csv
│   ├── ICRA2026_Paper_List.md
│   └── ICRA2026_Paper_List_with_Abstract.csv
├── IROS/
│   ├── README.md
│   ├── IROS2023_Paper_List.md
│   ├── IROS2023_Paper_List_with_Abstract.csv
│   ├── IROS2024_Paper_List.md
│   ├── IROS2024_Paper_List_with_Abstract.csv
│   ├── IROS2025_Paper_List.md
│   └── IROS2025_Paper_List_with_Abstract.csv
├── MICCAI/
│   ├── README.md
│   ├── MICCAI2021_Paper_List_with_Abstract.csv
│   ├── MICCAI2022_Paper_List_with_Abstract.csv
│   ├── MICCAI2023_Paper_List_with_Abstract.csv
│   ├── MICCAI2024_Paper_List_with_Abstract.csv
│   └── MICCAI2025_Paper_List_with_Abstract.csv
└── scripts/
    └── scrape_miccai.py   # regenerates the MICCAI CSVs (see MICCAI/README.md)
```

Naming convention:

- `<CONF><YEAR>_Paper_List.md` — Markdown paper list.
- `<CONF><YEAR>_Paper_List_with_Abstract.csv` — CSV with abstracts.

## `.md` file structure

Each Markdown file starts with a short header (title, source link, and — for
some years — a note about GitHub's display limits or a keyword-frequency
summary table), followed by a single pipe-delimited table of papers.

The table columns differ slightly by year:

| File | Columns |
| --- | --- |
| `ICRA/ICRA2023_Paper_List.md` | `Title \| Authors \| Organisation \| Session` |
| `ICRA/ICRA2024_Paper_List.md` | `Title \| Authors \| Session` |
| `ICRA/ICRA2025_Paper_List.md` | `Title \| Authors \| Session` |
| `ICRA/ICRA2026_Paper_List.md` | `Title \| Authors \| Session` |
| `IROS/IROS2023_Paper_List.md` | `Title \| Authors` (preceded by a keyword-count table) |
| `IROS/IROS2024_Paper_List.md` | `Title \| Authors` |
| `IROS/IROS2025_Paper_List.md` | `Title \| Authors \| Session` |

Column meanings:

- **Title** — the paper title.
- **Authors** — semicolon- or comma-separated author names (typically
  `Last, First`).
- **Organisation** — author affiliations (ICRA 2023 only).
- **Session** — the program session the paper is presented in. Where present,
  this doubles as the paper's topical category.

> Note: because these tables can be very large, GitHub may truncate the rendered
> view. Download the raw `.md` file to see the complete list.

## `_with_Abstract.csv` file structure

The CSV files carry the same papers plus the **abstract**, and depending on the
year also **keywords** and/or **affiliations**. Column order and presence of a
header row vary by file:

| File | Header row | Columns (in order) |
| --- | --- | --- |
| `ICRA/ICRA2023_..._with_Abstract.csv` | yes | `Title, Authors, Organisation, Session, Abstract` |
| `ICRA/ICRA2024_..._with_Abstract.csv` | no  | `Title, Authors, Affiliation, Session, Abstract` |
| `ICRA/ICRA2025_..._with_Abstract.csv` | yes | `Session, Paper Title, Author List, Keywords, Abstract` |
| `ICRA/ICRA2026_..._with_Abstract.csv` | yes | `Session, Paper Title, Author List, Affiliation, Keywords, Abstract` |
| `IROS/IROS2023_..._with_Abstract.csv` | no  | `Title, Authors (with affiliation), Keywords, Abstract` |
| `IROS/IROS2024_..._with_Abstract.csv` | no  | `Title, Authors, (Keywords), (Abstract)` |
| `IROS/IROS2025_..._with_Abstract.csv` | yes | `Session, Paper Title, Author List, Keywords, Abstract` |
| `MICCAI/MICCAI2021–2025_..._with_Abstract.csv` | yes | `Title, Authors, Topics, Abstract, Code, Dataset, PDF, Paper Page` |

The MICCAI files all share one schema (generated by
[`scripts/scrape_miccai.py`](scripts/scrape_miccai.py)); see
[MICCAI/README.md](MICCAI/README.md) for details.

Column meanings:

- **Title / Paper Title** — the paper title.
- **Authors / Author List** — semicolon-separated authors. In IROS 2023 each
  author is paired with an affiliation and authors are newline-separated within
  the cell.
- **Organisation / Affiliation** — author affiliations (where present).
- **Session** — the program session / topical category (where present).
- **Keywords** — topical keywords. In the 2025/IROS files the cell value is
  prefixed with the literal text `Keywords: `.
- **Abstract** — the paper abstract. In the 2025/IROS files the cell value is
  prefixed with the literal text `Abstract: `.
- **Topics** (MICCAI) — the paper's topic categories, `; `-separated.
- **Code / Dataset** (MICCAI) — code-repository and dataset URLs where the
  authors provided them, `;`-separated; empty otherwise.
- **PDF** (MICCAI) — the open-access PDF link (2024 – 2025) or, where no PDF is
  published, the paper's DOI / SpringerLink (2021 – 2023).
- **Paper Page** (MICCAI) — the per-paper detail page the record was scraped
  from.

Notes / caveats:

- Files without a header row (ICRA 2024, IROS 2023, IROS 2024) begin directly
  with the first data row — apply the column layout above when parsing.
- Some ICRA 2025 / IROS 2025 rows contain trailing empty columns.
- IROS 2024 rows may have empty keyword/abstract fields.
- Fields are standard double-quoted CSV; abstracts and multi-author cells can
  span multiple physical lines, so parse with a CSV reader rather than
  line-by-line splitting.
