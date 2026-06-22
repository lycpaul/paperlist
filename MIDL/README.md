# MIDL Paper Lists

Accepted-paper lists for the **MIDL** (Medical Imaging with Deep Learning)
conference. Each year's data is provided as a
`MIDL<YEAR>_Paper_List_with_Abstract.csv` file containing the full records,
including abstracts. Both **oral** and **poster** acceptances are included.

## Statistics

| Year | Papers | Oral | Poster | With TL;DR | With community impl. |
| --- | --- | --- | --- | --- | --- |
| 2026 | 200 | 0 | 200 | 117 | 0 |
| 2025 | 109 | 32 | 77 | 79 | 0 |
| 2024 | 117 | 36 | 81 | 0 | 0 |
| 2023 | 112 | 35 | 77 | 77 | 38 |

> MIDL 2026 oral/poster splits were not yet finalized on OpenReview at scrape
> time, so all 2026 records currently show as posters. Re-running the scraper
> will pick up the final designations.
>
> Community-implementation links (CatalyzeX) are only exposed by the OpenReview
> **v1** API used for 2023; the **v2** API (2024 onward) loads them client-side
> and does not return them as note content, so that column is empty for those
> years.

## Source & credits

The data is built from the official MIDL accepted-paper listings on
[OpenReview](https://openreview.net/). All credit for the original paper
listings goes to the MIDL organizers and the respective authors.

| Year | Source |
| --- | --- |
| MIDL 2026 | https://openreview.net/group?id=MIDL.io/2026/Conference |
| MIDL 2025 | https://openreview.net/group?id=MIDL.io/2025/Conference |
| MIDL 2024 | https://openreview.net/group?id=MIDL.io/2024/Conference |
| MIDL 2023 | https://openreview.net/group?id=MIDL.io/2023/Conference |

## CSV columns

Every `MIDL<YEAR>_Paper_List_with_Abstract.csv` has a header row and the same
nine columns:

| Column | Description |
| --- | --- |
| `Title` | Paper title. |
| `Authors` | `;`-separated author names. |
| `Session` | Acceptance type: `Oral` or `Poster`. |
| `Keywords` | `;`-separated author keywords. |
| `TL;DR` | One-line author summary, when provided. |
| `Abstract` | Full abstract. |
| `Community Implementations` | CatalyzeX code-listing URL, when available (2023 only). |
| `PDF` | OpenReview PDF link. |
| `Paper Page` | The OpenReview forum page for the paper. |

## Regenerating the data

The CSVs are produced by [`../scripts/scrape_midl.py`](../scripts/scrape_midl.py)
(Python standard library only — no dependencies). It reads the OpenReview API,
automatically selecting the v1 (2023) or v2 (2024+) endpoint per year.

```bash
python scripts/scrape_midl.py                # all years 2023-2026
python scripts/scrape_midl.py --year 2025    # a single edition
python scripts/scrape_midl.py --limit 5      # quick smoke test
```

Raw API responses are cached under `MIDL/.cache/<year>.json`, so re-runs are
fast. Delete the cache to force a fresh fetch.
