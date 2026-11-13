import json
from django.core.paginator import InvalidPage
from .pagination import CountedPaginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET
from django.utils.translation import override
from rest_framework.exceptions import ValidationError
from .models import HistoryRecord
from .queries import CONTEXT_RULE, PAGE_SIZE, filtered_records, parse_scope, scope_counts, temporal_context
from .research import load_research, research_card


@require_GET
def home(request):
    cards, analysis = load_research()
    return render(request, "histories/home.html", {"cards": cards, "quality": analysis["profile"]})


@require_GET
def card_detail(request, slug):
    card = research_card(slug)
    examples = {r.id: r for r in HistoryRecord.objects.filter(id__in=[e["id"] for e in card["examples"]]).defer("source_data")}
    for item in card["examples"]:
        item["record"] = examples.get(item["id"])
    return render(request, "histories/card.html", {"card": card, "rule": json.dumps(card["selection_rule"], ensure_ascii=False, indent=2)})


@require_GET
def records(request):
    context = {"filters": request.GET, "languages": list(HistoryRecord.objects.order_by("user_language").values_list("user_language", flat=True).distinct())}
    try:
        with override("ru"):
            scope = parse_scope(request.GET)
    except ValidationError as exc:
        labels = {
            "q": "Поиск по тексту", "id": "ID записи", "start": "С даты",
            "end": "По дату включительно", "role": "Роль", "language": "Язык",
            "deleted": "Состояние архива", "page": "Страница", "non_field_errors": "",
        }
        context["errors"] = [
            {"label": labels.get(field, "Фильтр"), "message": str(message)}
            for field, messages in exc.detail.items()
            for message in messages
        ]
        return render(request, "histories/records.html", context, status=400)
    qs = filtered_records(scope)
    counts = scope_counts(qs)
    pager = CountedPaginator(qs.defer("source_data"), PAGE_SIZE, counts["records"])
    try:
        page = pager.page(scope["page"])
    except InvalidPage:
        raise Http404("Страница не найдена")
    params = request.GET.copy()
    params.pop("page", None)
    context.update({"scope": scope, "page": page, "counts": counts, "query": params.urlencode()})
    return render(request, "histories/records.html", context)


@require_GET
def record_detail(request, pk):
    record = get_object_or_404(HistoryRecord, pk=pk)
    before, after = temporal_context(record)
    return render(request, "histories/record.html", {"record": record, "before": before, "after": after,
                  "context_rule": CONTEXT_RULE, "source_json": json.dumps(record.source_data, ensure_ascii=False, indent=2)})

