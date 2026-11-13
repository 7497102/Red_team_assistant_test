import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from time import perf_counter

import ijson
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection
from django.utils import timezone

from histories.models import HistoryRecord, ImportRun


REQUIRED_FIELDS = {
    "id", "usersid_hash", "role", "text", "actions", "createdAt", "updatedAt",
    "deletedAt", "userLanguage", "personality", "type", "internet", "timeSTT",
    "timeCache", "timeGPT", "user_request_type", "ai_response_type", "stt_quality", "ai_quality",
}


def validate_record(row):
    if not isinstance(row, dict) or not REQUIRED_FIELDS.issubset(row):
        raise ValueError("Record must be an object containing all source fields")
    if type(row["id"]) is not int or not -(2**63) <= row["id"] < 2**63:
        raise ValueError("id must be a signed 64-bit integer")
    for field in ("usersid_hash", "role", "text", "actions"):
        if not isinstance(row[field], str):
            raise ValueError(f"{field} must be a string")
    for field, limit in (("usersid_hash", 128), ("role", 32), ("userLanguage", 32)):
        value = row[field]
        if value is None and field == "userLanguage":
            continue
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"Invalid {field}; expected a string of at most {limit} characters")
    if not row["usersid_hash"] or row["role"] not in {"user", "assistant"}:
        raise ValueError("Empty user key or unsupported role")
    for field in ("createdAt", "updatedAt", "deletedAt"):
        value = row[field]
        if value is None and field == "deletedAt":
            continue
        if not isinstance(value, str) or len(value) != 19:
            raise ValueError(f"Invalid {field}; expected YYYY-MM-DD HH:MM:SS")
        parsed = datetime.fromisoformat(value)
        if parsed.isoformat(sep=" ", timespec="seconds") != value:
            raise ValueError(f"Invalid {field} format")


def insert_batch(rows):
    existing = HistoryRecord.objects.only("id", "source_data").in_bulk([row["id"] for row in rows])
    new = []
    for row in rows:
        previous = existing.get(row["id"])
        if previous is not None:
            if previous.source_data != row:
                raise ValueError(f"Existing ID {row['id']} has different source content")
            continue
        new.append(HistoryRecord(
            id=row["id"], usersid_hash=row["usersid_hash"], role=row["role"],
            text=row["text"], actions=row["actions"], created_at=row["createdAt"],
            updated_at=row["updatedAt"], deleted_at=row["deletedAt"],
            user_language=row["userLanguage"], source_data=row,
        ))
    HistoryRecord.objects.bulk_create(new, batch_size=500)
    return len(new)


class Command(BaseCommand):
    help = "Stream-import history JSON atomically, preserving source IDs and all fields."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, **options):
        # DEBUG SQL capture would retain huge INSERT statements in memory.
        original_debug = settings.DEBUG
        settings.DEBUG = False
        try:
            return self.import_file(**options)
        finally:
            settings.DEBUG = original_debug

    def import_file(self, **options):
        started = perf_counter()
        path = options["path"].resolve()
        batch_size = options["batch_size"]
        if not 1 <= batch_size <= 10000:
            raise CommandError("--batch-size must be between 1 and 10000")
        count = inserted = active = 0
        roles = Counter()
        seen_ids, keys = set(), set()
        minimum = maximum = None
        try:
            # Use a sibling profile when supplied, including its content hash.
            profile_path = path.with_name("dataset-profile.json")
            profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else None
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
                source_bytes = stream.tell()
                if profile and profile["sha256"] != digest:
                    raise ValueError("File SHA-256 does not match the supplied dataset profile")
                stream.seek(0)
                with transaction.atomic():
                    batch = []
                    for row in ijson.items(stream, "threadhistories.item", use_float=True):
                        validate_record(row)
                        if row["id"] in seen_ids:
                            raise ValueError(f"Duplicate ID {row['id']} within source file")
                        seen_ids.add(row["id"])
                        keys.add(row["usersid_hash"])
                        count += 1
                        roles[row["role"]] += 1
                        active += row["deletedAt"] is None
                        created = row["createdAt"]
                        minimum = min(minimum, created) if minimum else created
                        maximum = max(maximum, created) if maximum else created
                        batch.append(row)
                        if len(batch) >= batch_size:
                            inserted += insert_batch(batch)
                            batch = []
                        if count % 50000 == 0:
                            self.stdout.write(f"Validated {count:,} records (transaction pending)")
                    if not count:
                        raise ValueError("No records found in threadhistories array")
                    if batch:
                        inserted += insert_batch(batch)
                    actual = {
                        "records": count, "unique_ids": len(seen_ids),
                        "unique_usersid_hash": len(keys), "roles": dict(roles),
                        "createdAt_min": minimum, "createdAt_max": maximum,
                        "deletedAt_null": active, "deletedAt_nonnull": count - active,
                    }
                    if profile:
                        for field, value in actual.items():
                            if profile[field] != value:
                                raise ValueError(f"Profile mismatch for {field}: {value!r}")
                    ImportRun.objects.update_or_create(sha256=digest, defaults={
                        "source_path": str(path), "source_bytes": source_bytes,
                        "record_count": count, "inserted_count": inserted,
                        "unchanged_count": count - inserted,
                        "duration_seconds": perf_counter() - started,
                        "completed_at": timezone.now(),
                    })
            # Refresh planner statistics after a successful bulk load.
            if inserted:
                with connection.cursor() as cursor:
                    cursor.execute("ANALYZE histories_historyrecord")
            self.stdout.write(self.style.SUCCESS(
                f"Validated {count:,}; inserted {inserted:,}; unchanged {count-inserted:,}; "
                f"keys {len(keys):,}; deletedAt=null {active:,}; "
                f"elapsed {perf_counter()-started:.2f}s; SHA-256 {digest}"
            ))
        except (OSError, ValueError, OverflowError, ijson.JSONError) as exc:
            raise CommandError(f"Import failed; no changes committed: {exc}") from exc
