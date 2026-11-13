from django.db import models
from django.utils import timezone


class HistoryRecord(models.Model):
    """Immutable source event; a key is not a verified person or conversation."""

    id = models.BigIntegerField(primary_key=True)
    usersid_hash = models.CharField(max_length=128)
    role = models.CharField(max_length=32, db_index=True)
    text = models.TextField(blank=True)
    actions = models.TextField(blank=True)
    # ISO-like source strings sort chronologically and preserve unknown timezone.
    created_at = models.CharField(max_length=19, db_index=True)
    updated_at = models.CharField(max_length=19)
    deleted_at = models.CharField(max_length=19, null=True, blank=True, db_index=True)
    user_language = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    source_data = models.JSONField()

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["created_at", "id"], name="history_time_id"),
            models.Index(fields=["role", "user_language", "deleted_at", "usersid_hash", "created_at", "id"], name="history_scope_cover"),
            models.Index(fields=["usersid_hash", "created_at", "id"], name="history_key_time_id"),
        ]

    def __str__(self):
        return f"{self.id} · {self.role} · {self.created_at}"


class ImportRun(models.Model):
    """Latest successful validation/import of a source file, identified by content."""

    sha256 = models.CharField(max_length=64, primary_key=True)
    source_path = models.TextField()
    source_bytes = models.BigIntegerField()
    record_count = models.PositiveIntegerField()
    inserted_count = models.PositiveIntegerField()
    unchanged_count = models.PositiveIntegerField()
    duration_seconds = models.FloatField()
    completed_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.sha256[:12]} · {self.record_count} records"
