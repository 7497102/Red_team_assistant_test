from django.shortcuts import get_object_or_404
from .pagination import RecordPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import HistoryRecord
from .queries import CONTEXT_RULE, filtered_records, parse_scope, scope_counts, temporal_context
from .research import load_research, research_card
from .serializers import RecordListSerializer, RecordDetailSerializer, RecordContextSerializer


class ReadOnlyAPI(APIView):
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]


class RecordsAPI(ReadOnlyAPI):
    def get(self, request):
        scope = parse_scope(request.query_params)
        qs = filtered_records(scope)
        counts = scope_counts(qs)
        pager = RecordPagination(counts["records"])
        records = pager.paginate_queryset(qs.defer("source_data"), request)
        response = pager.get_paginated_response(RecordListSerializer(records, many=True).data)
        response.data.update({"scope": scope, "counts": counts, "ordering": ["created_at", "id"]})
        return response


class RecordAPI(ReadOnlyAPI):
    def get(self, request, pk):
        record = get_object_or_404(HistoryRecord, pk=pk)
        before, after = temporal_context(record)
        return Response({"record": RecordDetailSerializer(record).data, "context_rule": CONTEXT_RULE,
                         "before": RecordContextSerializer(before, many=True).data,
                         "after": RecordContextSerializer(after, many=True).data})


class ResearchAPI(ReadOnlyAPI):
    def get(self, request):
        cards, analysis = load_research()
        return Response({"scope_mode": "fixed; explorer filters do not change these findings", "cards": cards,
                         "quality": analysis["profile"]})


class ResearchDetailAPI(ReadOnlyAPI):
    def get(self, request, slug):
        return Response(research_card(slug))
