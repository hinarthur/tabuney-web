# game/sync_models.py
"""
單一 SyncLog model — 追蹤每次同步操作，不修改任何既有 model。
"""
import uuid
from django.db import models
from django.utils import timezone


class GameSyncLog(models.Model):
    """每次同步操作的紀錄"""

    class SyncType(models.TextChoices):
        DELTA = "delta", "Delta (差異同步)"
        FULL = "full", "Full (全量同步)"
        MANUAL = "manual", "Manual (手動同步)"

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial (部分成功)"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sync_type = models.CharField(max_length=20, choices=SyncType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)

    # 這次 delta sync 的基準點
    since = models.DateTimeField(null=True, blank=True, help_text="Delta sync 從此時間點之後取資料")

    # 統計
    records_sent = models.IntegerField(default=0)
    media_sent = models.IntegerField(default=0)
    qdrant_synced = models.BooleanField(default=False)

    # 詳細資訊
    details = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Game Sync Log"
        verbose_name_plural = "Game Sync Logs"

    def __str__(self):
        return f"[{self.sync_type}] {self.status} @ {self.created_at:%Y-%m-%d %H:%M}"

    def mark_success(self, **kwargs):
        self.status = self.Status.SUCCESS
        self.finished_at = timezone.now()
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.save()

    def mark_failed(self, error_msg):
        self.status = self.Status.FAILED
        self.error = str(error_msg)[:5000]
        self.finished_at = timezone.now()
        self.save()

    def mark_partial(self, error_msg="", **kwargs):
        self.status = self.Status.PARTIAL
        self.error = str(error_msg)[:5000]
        self.finished_at = timezone.now()
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.save()
