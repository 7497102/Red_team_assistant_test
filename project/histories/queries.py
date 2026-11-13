"""Shared scope and context logic for HTML and REST consumers."""
from django.db.models import Count, F, Func, Q
from django.db.models.expressions import RawSQL
from rest_framework import serializers
from .models import HistoryRecord

PAGE_SIZE = 50
CONTEXT_SIZE = 5


class ScopeSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=200)
    id = serializers.IntegerField(required=False, min_value=0, max_value=2**63-1)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    role = serializers.ChoiceField(choices=["", "user", "assistant"], required=False)
    language = serializers.CharField(required=False, allow_blank=True, max_length=32)
    deleted = serializers.ChoiceField(choices=["all", "null", "filled"], default="all")
    page = serializers.IntegerField(default=1, min_value=1, max_value=1000000)

    def validate(self, attrs):
        if attrs.get("start") and attrs.get("end") and attrs["start"] > attrs["end"]:
            raise serializers.ValidationError("Начальная дата должна быть не позже конечной.")
        return attrs


def parse_scope(params):
    # Empty form fields are equivalent to omitted filters.
    values = {k: v for k, v in params.items() if v != ""}
    serializer = ScopeSerializer(data=values)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def filtered_records(scope):
    qs = HistoryRecord.objects.all()
    if scope.get("q"):
        # SQLite's built-in LOWER/NOCASE do not casefold Cyrillic.
        needle = scope["q"].casefold()
        # FTS narrows candidates; the exact predicate below preserves literal semantics.
        if len(needle) >= 3 and "\x00" not in needle:
            phrase = '"' + needle.replace('"', '""') + '"'
            qs = qs.filter(pk__in=RawSQL(
                "SELECT rowid FROM history_text_search WHERE history_text_search MATCH %s",
                [phrase],
            ))
        qs = qs.alias(search_text=Func(F("text"), function="history_casefold")).filter(search_text__contains=scope["q"].casefold())
    if "id" in scope:
        qs = qs.filter(pk=scope["id"])
    if scope.get("start"):
        qs = qs.filter(created_at__gte=f"{scope['start'].isoformat()} 00:00:00")
    if scope.get("end"):
        qs = qs.filter(created_at__lte=f"{scope['end'].isoformat()} 23:59:59")
    if scope.get("role"):
        qs = qs.filter(role=scope["role"])
    if scope.get("language"):
        qs = qs.filter(user_language__isnull=True) if scope["language"] == "__null__" else qs.filter(user_language=scope["language"])
    if scope["deleted"] != "all":
        qs = qs.filter(deleted_at__isnull=scope["deleted"] == "null")
    return qs.order_by("created_at", "id")


def scope_counts(qs):
    return qs.aggregate(records=Count("id"), keys=Count("usersid_hash", distinct=True),
                        user=Count("id", filter=Q(role="user")), assistant=Count("id", filter=Q(role="assistant")))


def temporal_context(record):
    qs = HistoryRecord.objects.filter(usersid_hash=record.usersid_hash).defer("source_data")
    before = list(qs.filter(Q(created_at__lt=record.created_at) | Q(created_at=record.created_at, id__lt=record.id))
                  .order_by("-created_at", "-id")[:CONTEXT_SIZE])
    after = list(qs.filter(Q(created_at__gt=record.created_at) | Q(created_at=record.created_at, id__gt=record.id))
                 .order_by("created_at", "id")[:CONTEXT_SIZE])
    return list(reversed(before)), after


CONTEXT_RULE = "До 5 предыдущих и 5 следующих записей того же ключа, порядок: createdAt, затем id. Весь архив, независимо от фильтров поиска. Это временной контекст, а не подтверждённый диалог; разрыв времени не ограничен."
