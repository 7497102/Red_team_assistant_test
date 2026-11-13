import json
from pathlib import Path
from django.conf import settings
from django.http import Http404


def load_research():
    root = Path(settings.BASE_DIR) / "research"
    cards = json.loads((root / "cards.json").read_text(encoding="utf-8"))
    analysis = json.loads((root / "generated" / "analysis.json").read_text(encoding="utf-8"))
    for card in cards:
        for example in card["examples"]:
            example["url"] = f"/records/{example['id']}/"
        card["percent"] = round(card["counts"]["message_fraction"] * 100, 3)
    return cards, analysis


def research_card(slug):
    cards, _ = load_research()
    for card in cards:
        if card["slug"] == slug:
            return card
    raise Http404("Исследование не найдено")
