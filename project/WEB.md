# Web interface and REST API

From `TZ project/project` with the virtual environment active:

```powershell
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. The application is a local read-only research tool.
Jazzmin administration remains available at `/admin/`. Browser assets are served
locally, with no CDN or paid API dependency.

## User path

1. `/` — research cards and data-quality summary.
2. `/research/media/` or `/research/repeats/` — rule, denominators, examples,
   counterexample, robustness calculation, and next experiment.
3. `/records/<id>/` — original fields and temporal context.
4. `/records/` — searchable, paginated archive with scope-aware counts.

Cards use the saved full-corpus research scope. Explorer filters do not alter
reviewed claims; this is explicitly labeled. Cards require the existing
`research/cards.json` and `research/generated/analysis.json` artifacts. If the
source data or research rules change, rerun analysis and review the cards.

Context contains up to five records before and after the selected record from
the same key, sorted by source timestamp and ID. It uses all archived records,
regardless of explorer filters. There is no maximum time-gap assumption, and
these records must not be presented as confirmed conversations.

## REST endpoints (GET only)

- `/api/records/` — up to 50 previews, total count, role/key counts, parsed scope,
  and next/previous page URLs.
- `/api/records/<id>/` — complete selected record and bounded temporal context.
- `/api/research/` — fixed-scope cards and data-quality summary.
- `/api/research/<slug>/` — one card with evidence links.

Supported record-list parameters: `q`, `id`, `start`, `end`, `role`, `language`,
`deleted`, `page`. Dates use YYYY-MM-DD, both ends inclusive. `deleted` is `all`
(default), `null`, or `filled`; `language=__null__` selects missing metadata.
Filters combine with AND. Ordering is `created_at, id`. Search is a literal
substring with Unicode casefolding, including Cyrillic. SQLite FTS5 indexes casefolded trigrams to narrow candidates for queries of at
least three characters. The exact casefolded substring predicate then verifies
candidates. Shorter queries use a scan to preserve the same semantics. No stemming or transliteration is implied.

Invalid filters return 400. Unknown IDs/pages return 404. Mutation methods return
405. Empty lists return 200 with zero counts. List previews are limited to 500
characters and report whether truncation occurred. Source texts are escaped in
HTML and are never interpreted as markup, code, or processing instructions.

## Verification

```powershell
python manage.py check
python manage.py test histories
```

24 tests cover import/analysis plus combined filters, counts, casefold search,
pagination, context isolation/tie ordering, invalid input, HTML escaping, fixed
research scope, and read-only endpoints. Full-database HTTP checks confirmed
successful rendering and 6,875 results for `/api/records/?deleted=null`.
Browser checks covered the main pages, filters, pagination, empty results, date errors, and the form at 390 px width. Authenticated Jazzmin pages have not been visually reviewed; full wide-screen visual inspection was limited by screenshot capture failure.
