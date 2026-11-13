"""Use the scope aggregate's exact count instead of issuing a duplicate COUNT."""
from django.core.paginator import Paginator
from django.db.models import Subquery
from .models import HistoryRecord
from rest_framework.pagination import PageNumberPagination
from .queries import PAGE_SIZE


class CountedPaginator(Paginator):
    def __init__(self, object_list, per_page, total):
        super().__init__(object_list, per_page)
        self.count = total


    def _get_page(self, object_list, number, paginator):
        # Skip through a narrow ID index before loading the 50 wide source rows.
        page_ids = object_list.values("pk")
        records = HistoryRecord.objects.filter(pk__in=Subquery(page_ids)).defer("source_data").order_by("created_at", "id")
        return super()._get_page(records, number, paginator)


class RecordPagination(PageNumberPagination):
    page_size = PAGE_SIZE

    def __init__(self, total):
        self.total = total

    def django_paginator_class(self, queryset, page_size):
        return CountedPaginator(queryset, page_size, self.total)
