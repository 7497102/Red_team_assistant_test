# History import

Run from the `TZ project` directory using the existing virtual environment:

```powershell
.\venv\Scripts\python.exe project\manage.py migrate
.\venv\Scripts\python.exe project\manage.py import_histories "assistant-test-20pct-users\data\threadhistories_20pct_users.json"
.\venv\Scripts\python.exe project\manage.py test histories
```

Repeat the import command to verify idempotency. The second successful run should
report 0 inserted and 260,232 unchanged records. The command records the file hash,
source size, counts, and elapsed processing time in `ImportRun`. Its duration excludes
the final transaction commit; the terminal reports the total command processing time.

## Storage and validation

- Records are stored in `project/db.sqlite3` with the original ID as primary key.
- All 19 source fields are preserved in `source_data`. Frequently queried fields
  also have dedicated columns; source names such as `createdAt` map to `created_at`.
- Source date strings remain unchanged because the timezone is undocumented.
- Entire history is included by default, including populated `deletedAt` values.
- JSON is streamed in batches. A transaction rolls back all inserts on invalid data.
- Duplicate IDs inside one file are rejected. Existing identical records are accepted;
  existing IDs with changed content are rejected rather than overwritten.
- A sibling `dataset-profile.json`, when present, is used to verify SHA-256 and
  the source counts, roles, keys, dates, and deletion states before commit.
- User keys are not verified people, and records are not confirmed conversations.

## Admin inspection

Start `project/manage.py runserver` using the virtual environment and open `/admin/`.
`History records` and `Import runs` are read-only. Records support text/ID search,
role and language filters, archive scope, and pagination. Selecting `deletedAt=null`
must yield 6,875 records; the full supplied corpus must contain 260,232 records.

The research cards, public record explorer, and REST endpoints are subsequent steps.

## Verified on 2026-11-13

- Initial full import: 260,232 inserted, 19.94 seconds reported elapsed time.
- Repeat full import: 0 inserted, 260,232 unchanged, 13.95 seconds.
- Independent database queries confirmed 999 keys, 130,934 user records,
  129,298 assistant records, and 6,875 records with `deletedAt=null`.
- Date range: `2024-09-06 09:51:13` to `2026-11-04 14:50:41` (timezone unknown).
- SHA-256 matched the supplied profile.
- Eight automated tests passed. Django system checks passed and no model changes
  were missing migrations.
