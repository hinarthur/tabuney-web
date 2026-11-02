"""
問卷：題目在 admin 編輯，回答匿名也能送。

  edition 問卷 —— 掛在 edition 所有分頁的浮動按鈕，每個 edition 各填一次，長期使用
  site 問卷    —— 非 edition 頁的浮動按鈕，只在 beta 期間開放（見 views.SurveyView）

資料只存在 VPS：這個 app 不在 game/sync_service.py 的同步白名單裡。指向 Edition 的
FK 一律 SET_NULL 並另存名稱快照，edition 被刪也不會連帶刪掉回答。

多語文字（題目、選項、說明）存成 {lang: text} 的 JSON，缺的語言退回英文。
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

LANG_CODES = [code for code, _ in settings.LANGUAGES]
FALLBACK_LANG = "en"


def localized(texts, lang):
    """從 {lang: text} 取出指定語言，缺的退回英文，再缺就拿第一個有值的。"""
    if not isinstance(texts, dict):
        return ""
    for code in (lang, FALLBACK_LANG):
        value = (texts.get(code) or "").strip()
        if value:
            return value
    return next((v.strip() for v in texts.values() if isinstance(v, str) and v.strip()), "")


def missing_langs(texts):
    """這組多語文字還缺哪些介面語言（給 admin 顯示與 DeepL 補齊用）。"""
    texts = texts if isinstance(texts, dict) else {}
    return [code for code in LANG_CODES if not (texts.get(code) or "").strip()]


class Survey(models.Model):
    class Kind(models.TextChoices):
        EDITION = "edition", "Edition 問卷"
        SITE = "site", "全站問卷（beta）"

    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    name = models.CharField(max_length=200, verbose_name="名稱（內部用）")
    # 同一 kind 同時只能有一份啟用中。要改題目就停用舊的、建新的一份——
    # 已有人回答的題目改字會讓舊答案的語意跟著變。
    is_active = models.BooleanField(default=False, verbose_name="啟用中")
    title = models.JSONField(default=dict, blank=True, verbose_name="標題（多語）",
                             help_text='例：{"en": "Quick survey", "zh": "小問卷"}')
    intro = models.JSONField(default=dict, blank=True, verbose_name="開頭說明（多語）")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Survey"
        verbose_name_plural = "Surveys"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind"], condition=Q(is_active=True),
                name="uq_survey_one_active_per_kind",
            ),
        ]

    def __str__(self):
        return f"[{self.get_kind_display()}] {self.name}{'（啟用中）' if self.is_active else ''}"

    def clean(self):
        if self.is_active and Survey.objects.filter(
            kind=self.kind, is_active=True
        ).exclude(pk=self.pk).exists():
            raise ValidationError({"is_active": "同一種問卷只能有一份啟用中，請先停用另一份。"})


class SurveyQuestion(models.Model):
    class QType(models.TextChoices):
        SINGLE = "single", "單選"
        MULTI = "multi", "複選"
        TEXT = "text", "文字"

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField(default=0, verbose_name="順序")
    qtype = models.CharField(max_length=10, choices=QType.choices, verbose_name="題型")
    required = models.BooleanField(default=False, verbose_name="必填")
    text = models.JSONField(default=dict, verbose_name="題目（多語）",
                            help_text='例：{"en": "How easy was it?", "zh": "好上手嗎？"}')

    class Meta:
        verbose_name = "Survey question"
        verbose_name_plural = "Survey questions"
        ordering = ["survey", "order", "id"]

    def __str__(self):
        return f"Q{self.order} {localized(self.text, 'zh') or localized(self.text, 'en')}"


class SurveyChoice(models.Model):
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name="choices")
    order = models.PositiveIntegerField(default=0, verbose_name="順序")
    text = models.JSONField(default=dict, verbose_name="選項（多語）")
    # 「其他」選項：選了之後前端多出一個輸入欄，填的字存在 SurveyAnswer.text
    is_other = models.BooleanField(default=False, verbose_name="Other (shows a text field)")

    class Meta:
        verbose_name = "Survey choice"
        verbose_name_plural = "Survey choices"
        ordering = ["question", "order", "id"]

    def __str__(self):
        return localized(self.text, "zh") or localized(self.text, "en")


class SurveyResponse(models.Model):
    # PROTECT：有人回答過的問卷刪不掉，只能停用
    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name="responses")
    edition = models.ForeignKey(
        "game.Edition", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="survey_responses",
    )
    edition_name = models.CharField(max_length=300, blank=True, verbose_name="Edition（送出時快照）")
    # null＝匿名。匿名不記任何識別碼（IP、session_key 都沒有），也就無法防重複，
    # 「填過不再出現」對匿名者只靠瀏覽器的 localStorage。
    member = models.ForeignKey(
        "member.Member", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="survey_responses",
    )
    lang = models.CharField(max_length=10, blank=True)
    # 從哪裡送出：edition 問卷是分頁名（flowchart / chat / script / info），全站問卷是 path
    page = models.CharField(max_length=200, blank=True)
    # 填到一半就離開時，前端把已答的題目先送出；必填題允許缺漏
    is_partial = models.BooleanField(default=False, verbose_name="Partial (left midway)")
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        verbose_name = "Survey response"
        verbose_name_plural = "Survey responses"
        ordering = ["-created_at"]

    def __str__(self):
        who = self.member or "匿名"
        where = f" · {self.edition_name}" if self.edition_name else ""
        return f"{self.survey.name}{where} · {who}"


class SurveyAnswer(models.Model):
    """一題一列；複選題每個選中的選項各一列，統計直接 GROUP BY choice。"""

    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name="answers")
    # PROTECT：有人回答過的題目與選項刪不掉，避免舊答案失去意義
    question = models.ForeignKey(SurveyQuestion, on_delete=models.PROTECT, related_name="answers")
    choice = models.ForeignKey(SurveyChoice, null=True, blank=True, on_delete=models.PROTECT,
                               related_name="answers")
    text = models.TextField(blank=True)

    class Meta:
        verbose_name = "Survey answer"
        verbose_name_plural = "Survey answers"

    def __str__(self):
        return str(self.choice) if self.choice_id else self.text[:50]
