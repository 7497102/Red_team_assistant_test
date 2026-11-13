import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from histories.analysis import VERSION, SEED, sample, screen, summarize
from histories.models import HistoryRecord, ImportRun


class Command(BaseCommand):
    help = "Reproduce quality profile and two exploratory research screens."

    def add_arguments(self, parser):
        parser.add_argument("--output", type=Path, default=None)
        parser.add_argument("--active-only", action="store_true")
        parser.add_argument("--exclude-key")

    def handle(self, *args, **options):
        qs = HistoryRecord.objects.all()
        if options["active_only"]:
            qs = qs.filter(deleted_at__isnull=True)
        if options["exclude_key"]:
            qs = qs.exclude(usersid_hash=options["exclude_key"])
        fields = ["id", "usersid_hash", "role", "text", "actions", "created_at", "deleted_at", "user_language"]
        rows = list(qs.order_by("usersid_hash", "created_at", "id").values(*fields).iterator(chunk_size=2000))
        if not rows:
            raise CommandError("No records in analysis scope")
        users = [r for r in rows if r["role"] == "user"]
        media, repeats = screen(rows)
        activity = Counter(r["usersid_hash"] for r in users)
        top = sorted(activity, key=lambda k: (-activity[k], k))[0] if activity else None
        reduced_users = [r for r in users if r["usersid_hash"] != top]
        # Excluding a whole key cannot change adjacency within another key.
        reduced_media = [r for r in media if r["usersid_hash"] != top]
        reduced_repeats = [r for r in repeats if r["usersid_hash"] != top]
        profile = {
            "records": len(rows), "roles": dict(Counter(r["role"] for r in rows)),
            "keys": len({r["usersid_hash"] for r in rows}),
            "date_min": min(r["created_at"] for r in rows), "date_max": max(r["created_at"] for r in rows),
            "months": dict(sorted(Counter(r["created_at"][:7] for r in rows).items())),
            "user_languages": dict(Counter(r["user_language"] or "<null>" for r in users)),
            "missing": {f: {"null": sum(r[f] is None for r in rows),
                "blank": sum(isinstance(r[f], str) and not r[f].strip() for r in rows)} for f in fields},
            "top10_user_message_fraction": sum(sorted(activity.values(), reverse=True)[:10])/len(users) if users else None,
        }
        result = {
            "rule_version": VERSION, "sample_seed": SEED,
            "source_hashes": list(ImportRun.objects.order_by("sha256").values_list("sha256", flat=True)),
            "scope": {"deleted_at": "null only" if options["active_only"] else "all historical records",
                      "excluded_key": options["exclude_key"], "timezone": "unknown"},
            "profile": profile, "media": summarize(media, users), "repeats": summarize(repeats, users),
            "repeat_windows": {str(s): summarize([r for r in repeats if r["gap_seconds"] <= s], users) for s in [30, 60, 120]},
            "repeat_without_intervening_assistant": sum(not r["intervening_assistant_ids"] for r in repeats),
            "exclude_most_active": {"key": top, "user_messages": activity.get(top, 0),
                "media": summarize(reduced_media, reduced_users), "repeats": summarize(reduced_repeats, reduced_users)},
        }
        suffix = "generated_active" if options["active_only"] else "generated"
        if options["exclude_key"]:
            suffix += "_excluded_" + hashlib.sha256(options["exclude_key"].encode()).hexdigest()[:12]
        out = options["output"] or settings.BASE_DIR / "research" / suffix
        out.mkdir(parents=True, exist_ok=True)
        (out / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        for name, matches in [("media", media), ("repeats", repeats)]:
            (out / f"{name}_matches.json").write_text(json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8")
        # Candidate review file is regenerated; keep completed reviews separately.
        review = []
        for topic, matches in [("media", media), ("repeats", repeats)]:
            ids = {r["id"] for r in matches}
            nonmatches = [r for r in users if r["id"] not in ids]
            for language in ["uz-UZ", "ru-RU"]:
                for group, pool, size in [("match", matches, 15), ("nonmatch", nonmatches, 10)]:
                    for row in sample([r for r in pool if r["user_language"] == language], size):
                        review.append({"topic": topic, "selection": group, "id": row["id"], "language": language,
                                       "text": row["text"], "decision": "pending", "comment": ""})
        by_id = {r["id"]: r for r in rows}
        repeat_by_id = {r["id"]: r for r in repeats}
        contexts = []
        for candidate in review:
            if candidate["topic"] == "repeats" and candidate["selection"] == "match":
                match = repeat_by_id[candidate["id"]]
                ids = [match["previous_id"], *match["intervening_assistant_ids"], match["id"]]
                contexts.append({"id": match["id"], "records": [by_id[i] for i in ids]})
        (out / "review_context.json").write_text(json.dumps(contexts, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "user_activity.json").write_text(json.dumps(dict(sorted(activity.items())), indent=2), encoding="utf-8")
        with (out / "review_candidates.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["topic", "selection", "id", "language", "text", "decision", "comment"])
            writer.writeheader()
            writer.writerows(review)
        self.stdout.write(json.dumps({"records": len(rows), "media": result["media"], "repeats": result["repeats"], "output": str(out)}, ensure_ascii=False))
