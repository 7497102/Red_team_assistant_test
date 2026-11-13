"""Versioned screening rules, not a classifier or verified failure detector."""
import heapq
import hashlib
import re
import unicodedata
from collections import Counter
from datetime import datetime

VERSION = "1.0"
SEED = "20261105"
MEDIA = re.compile(r"музык|мусиқ|musiq|qo['’ʻ‘`ʼ]?shiq|қўшиқ|песн|youtube|ютуб|yutub|радио|radio", re.I)
COMMAND = re.compile(r"включ|постав|откро|запуст|слуш|qo['’ʻ‘`ʼʻ]?y|eshit|och|yoq|қўй|эшит|оч|ёқ", re.I)

def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join("".join(" " if unicodedata.category(c)[0] in {"P", "S"} else c for c in text).split())

def media_match(text):
    return bool(MEDIA.search(text) and COMMAND.search(text))

def screen(rows, seconds=120):
    media, repeats = [], []
    previous = None
    previous_normalized = ""
    intervening = []
    for row in rows:
        if previous and row["usersid_hash"] != previous["usersid_hash"]:
            previous, intervening = None, []
        if row["role"] != "user":
            if previous:
                intervening.append(row["id"])
            continue
        if media_match(row["text"]):
            media.append(row)
        normalized = normalize(row["text"])
        if previous:
            gap = (datetime.fromisoformat(row["created_at"]) - datetime.fromisoformat(previous["created_at"])).total_seconds()
            if normalized and normalized == previous_normalized and 0 <= gap <= seconds:
                repeats.append({**row, "previous_id": previous["id"], "gap_seconds": gap,
                                "intervening_assistant_ids": list(intervening)})
        previous, intervening = row, []
        previous_normalized = normalized
    return media, repeats

def summarize(matches, users):
    return {"messages": len(matches), "keys": len({r["usersid_hash"] for r in matches}),
            "denominator_user_messages": len(users), "denominator_keys": len({r["usersid_hash"] for r in users}),
            "message_fraction": len(matches)/len(users) if users else None,
            "language_counts": dict(Counter(r["user_language"] or "<null>" for r in matches))}

def sample(rows, limit=15):
    # Stable hash ranking, independent of database query order.
    return heapq.nsmallest(limit, rows, key=lambda r: hashlib.sha256(f"{SEED}:{r['id']}".encode()).hexdigest())
