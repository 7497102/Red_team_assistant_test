from django.contrib import admin

from .models import HistoryRecord, ImportRun


class ArchiveStateFilter(admin.SimpleListFilter):
    title = "archive scope"
    parameter_name = "archive_scope"

    def lookups(self, request, model_admin):
        return [("null", "deletedAt=null"), ("filled", "deletedAt populated")]

    def queryset(self, request, queryset):
        if self.value() == "null":
            return queryset.filter(deleted_at__isnull=True)
        if self.value() == "filled":
            return queryset.filter(deleted_at__isnull=False)
        return queryset


class ReadOnlyAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HistoryRecord)
class HistoryRecordAdmin(ReadOnlyAdmin):
    list_display = ["id", "created_at", "role", "user_language", "text_preview"]
    list_filter = ["role", "user_language", ArchiveStateFilter]
    search_fields = ["=id", "=usersid_hash", "text"]
    list_per_page = 50
    show_full_result_count = False

    @admin.display(description="Text")
    def text_preview(self, obj):
        return obj.text[:120]


@admin.register(ImportRun)
class ImportRunAdmin(ReadOnlyAdmin):
    list_display = ["sha256", "record_count", "inserted_count", "duration_seconds", "completed_at"]
