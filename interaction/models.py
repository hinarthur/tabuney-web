from django.db import models
from django.utils import timezone
from member.models import Member
from game.models import Edition

# 喜好選項 (Rating Choices)
RATING_CHOICES = [
    ('amazing', '💘 迷戀 Amazing'),
    ('nice', '👍 不錯 Nice'),
    ('nah', '😕 算了吧 Nah'),
    ('nightmare', '💀 惡夢 Nightmare'),
]

# 分值對照 (Rating Scores)
# 用於未來推薦系統運算
RATING_SCORES = {
    'amazing': 4,
    'nice': 1,
    'nah': -1,
    'nightmare': -4,
}

# 收藏狀態 (Collection Status Choices)
COLLECTION_STATUS_CHOICES = [
    ('past', '🕰️ 曾有 Past'),
    ('owned', '📦 持有 Owned'),
    ('wish', '⭐ 想要 Wish'),
]

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Interaction(TimeStampedModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='interactions')
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name='interactions')
    
    rating = models.CharField(
        max_length=20, 
        choices=RATING_CHOICES, 
        blank=True, 
        null=True,
        help_text="用戶對此版本的喜好程度"
    )
    status = models.CharField(
        max_length=20, 
        choices=COLLECTION_STATUS_CHOICES, 
        blank=True, 
        null=True,
        help_text="用戶對此版本的收藏狀態"
    )

    class Meta:
        unique_together = ('member', 'edition')
        verbose_name = "Interaction"
        verbose_name_plural = "Interactions"

    def __str__(self):
        return f"{self.member} - {self.edition}"
