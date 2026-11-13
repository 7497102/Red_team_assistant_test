from rest_framework import serializers
from .models import HistoryRecord


class RecordListSerializer(serializers.ModelSerializer):
    preview = serializers.SerializerMethodField()
    text_truncated = serializers.SerializerMethodField()

    class Meta:
        model = HistoryRecord
        fields = ["id", "usersid_hash", "role", "created_at", "deleted_at", "user_language", "preview", "text_truncated"]

    def get_preview(self, obj):
        return obj.text[:500]

    def get_text_truncated(self, obj):
        return len(obj.text) > 500


class RecordDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoryRecord
        fields = ["id", "usersid_hash", "role", "text", "actions", "created_at", "updated_at", "deleted_at", "user_language", "source_data"]


class RecordContextSerializer(RecordDetailSerializer):
    class Meta(RecordDetailSerializer.Meta):
        fields = [f for f in RecordDetailSerializer.Meta.fields if f != "source_data"]
