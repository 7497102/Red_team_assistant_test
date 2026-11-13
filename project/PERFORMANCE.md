# Performance and quality review — 2026-11-13

## Measured changes

Three requests per route against the same full local database, Django test client,
DEBUG configuration unchanged. Median server-side elapsed time; browser paint,
network latency, cold-start latency, and concurrent load are not measured. No result cache.

| Route | Before (s) | After (s) | Speedup | SQL queries |
|---|---:|---:|---:|---:|
| `/records/` | 0.3327 | 0.1014 | 3.3x | 4 → 3 |
| `/api/records/` | 0.2481 | 0.1044 | 2.4x | 3 → 2 |
| `/api/records/?q=музыку&role=user` | 1.1302 | 0.0627 | 18.0x | 3 → 2 |
| `/api/records/?deleted=null` | 0.0257 | 0.0282 | 0.9x | 3 → 2 |
| `/api/records/?page=4000` | 0.6487 | 0.1007 | 6.4x | 3 → 2 |
| `/records/667989/` | 0.0036 | 0.0034 | 1.1x | 3 → 3 |
| `/research/media/` | 0.0023 | 0.0031 | 0.7x | 1 → 1 |

## Implementation

- SQLite FTS5 trigram index on casefolded text, populated by a migration.
  Transactional insert/update/delete triggers maintain it, including bulk operations.
  Original source fields are unchanged. Quoted, parameterized MATCH phrases prevent
  query text from becoming FTS operators. An exact predicate preserves literal matching.
- Short searches retain the original scan; they may still be slow on large scopes.
- Covering scope index plus chronological (created_at, id) index.
- Pagination reuses the exact aggregate count and selects IDs before loading wide rows.
  Page-number URLs and deterministic ordering remain unchanged; deep OFFSET remains O(n).
- SQLite planner statistics refreshed by migration and after a successful bulk import.
- Analysis normalizes each user text once and screens the corpus once. Smaller windows
  reuse the 120-second matches; excluding an entire key cannot change other keys’ adjacency.
- Bounded heap sampling preserves the deterministic selected IDs without sorting every candidate.
- Import compares only ID and source_data on reimport, and uses ISO date parsing with
  strict round-trip validation rather than repeated strptime/strftime calls.

## Validation

- 24 tests pass, including index maintenance, Unicode expansions (Straße → strasse),
  quoted text, literal wildcards, stable pages, query count, rollback and existing UI behavior.
- All six generated analysis artifacts are byte-identical before/after on the full corpus.
- Analysis elapsed time: 13.118 seconds before, 5.033 seconds after (one run each).
- Full-corpus search equivalence checked for music, YouTube, Uzbek spelling and special symbols.
- Repeat import: 0 inserted, 260232 unchanged; completed in 8.34 seconds.
- SQLite integrity_check: ok. No pending model migrations.

## Tradeoffs and operation

Database grew from 303.9 MiB to 437.9 MiB. Initial import now maintains a search index,
so it may take longer; only repeat-import timing was measured after this change.
The index requires SQLite with FTS5/trigram support (verified in the current environment).
All database writes must go through configured Django connections, which register the
Unicode function used by triggers. Future SQLite migrations that rebuild the source
table must preserve/recreate the search triggers.

Research still loads selected source columns into memory, not the full raw JSON;
this is appropriate for the supplied corpus but is not a constant-memory analytics engine.
No claim of production deployment hardening or independent linguistic validation is made.

From the project directory:

```powershell
python manage.py migrate
python manage.py test histories
python manage.py benchmark_histories
```

Review artifacts remain in `research/`. A local pre-change database backup and benchmark
inputs/results are retained under the workspace `work/` directory.
