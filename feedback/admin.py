from django import forms
from django.contrib import admin, messages
from django.db.models import Count
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from feedback.models import (
    LANG_CODES, Survey, SurveyAnswer, SurveyChoice, SurveyQuestion, SurveyResponse,
    localized, missing_langs,
)

# 後台以中文為主，列表與統計頁都用這個語言顯示題目
ADMIN_LANG = "zh"


# ─────────────────────────────────────────────
# 多語 JSON 欄位 → 每個語言一格輸入框
# ─────────────────────────────────────────────

class MultiLangForm(forms.ModelForm):
    """
    把 {lang: text} 的 JSONField 拆成每個語言一個欄位（例如 text_en、text_zh），
    存檔時再組回 JSON。用 multilang_form() 產生子類別。

    每語言的欄位必須在建立類別時就宣告：admin 的 fieldsets 會拿欄位名去比對
    form 的 declared_fields，在 __init__ 才加的欄位會被當成 model 不存在的欄位。
    """

    MULTILANG_FIELDS = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.MULTILANG_FIELDS:
            current = getattr(self.instance, name, None) or {}
            for code in LANG_CODES:
                if f"{name}_{code}" in self.fields:
                    self.fields[f"{name}_{code}"].initial = current.get(code, "")

    def clean(self):
        cleaned = super().clean()
        for name in self.MULTILANG_FIELDS:
            cleaned[name] = {
                code: (cleaned.get(f"{name}_{code}") or "").strip()
                for code in LANG_CODES
                if (cleaned.get(f"{name}_{code}") or "").strip()
            }
        return cleaned

    def save(self, commit=True):
        for name in self.MULTILANG_FIELDS:
            setattr(self.instance, name, self.cleaned_data[name])
        return super().save(commit=commit)


def _lang_fields(name, langs=LANG_CODES):
    return tuple(f"{name}_{code}" for code in langs)


def multilang_form(model, fields, multilang, textarea=(), base=MultiLangForm):
    attrs = {"MULTILANG_FIELDS": tuple(multilang)}
    for name in multilang:
        for code in LANG_CODES:
            widget = (forms.Textarea(attrs={"rows": 2, "cols": 60}) if name in textarea
                      else forms.TextInput(attrs={"size": 40}))
            attrs[f"{name}_{code}"] = forms.CharField(
                label=f"{code}", required=False, widget=widget,
            )
    attrs["Meta"] = type("Meta", (), {"model": model, "fields": tuple(fields)})
    return type(f"{model.__name__}MultiLangForm", (base,), attrs)


class _RequireTextMixin:
    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("text"):
            raise forms.ValidationError("至少要填一種語言（建議先填英文，其他用 DeepL 補齊）。")
        return cleaned


class _RequiredTextForm(_RequireTextMixin, MultiLangForm):
    pass


SurveyForm = multilang_form(Survey, ("kind", "name", "is_active"), ("title", "intro"), textarea=("intro",))
QuestionForm = multilang_form(SurveyQuestion, ("survey", "order", "qtype", "required"), ("text",),
                              base=_RequiredTextForm)
QuestionInlineForm = multilang_form(SurveyQuestion, ("order", "qtype", "required"), ("text",),
                                    base=_RequiredTextForm)
ChoiceForm = multilang_form(SurveyChoice, ("order", "is_other"), ("text",), base=_RequiredTextForm)


# ─────────────────────────────────────────────
# DeepL 補齊缺的語言
# ─────────────────────────────────────────────

def _fill_missing_langs(objects_and_fields):
    """
    objects_and_fields: [(obj, field_name), ...]。以英文為來源（沒有英文就用中文）
    把每個缺漏的語言翻好寫回，回傳 (補了幾格, 失敗幾格)。

    沿用流程圖翻譯的後端（game/rag/flowchart/i18n.py），目前只有 DeepL。
    """
    from game.rag.flowchart.i18n import _backend_batch, _get_backends

    backends = _get_backends()
    if not backends:
        raise RuntimeError("未設定任何翻譯後端（DEEPL_AUTH_KEY），無法翻譯。")

    # 依 (來源語言, 目標語言) 分組批次送出，省 API 呼叫次數
    jobs = {}
    for obj, field in objects_and_fields:
        texts = getattr(obj, field) or {}
        src = next((c for c in ("en", "zh") if (texts.get(c) or "").strip()), None)
        if src is None:
            continue
        for tgt in missing_langs(texts):
            jobs.setdefault((src, tgt), []).append((obj, field, texts[src]))

    filled = failed = 0
    dirty = set()
    for (src, tgt), items in jobs.items():
        results = _backend_batch([text for _, _, text in items], src, tgt, backends)
        for (obj, field, _), translated in zip(items, results):
            if not translated:
                failed += 1
                continue
            texts = dict(getattr(obj, field) or {})
            texts[tgt] = translated
            setattr(obj, field, texts)
            dirty.add(obj)
            filled += 1

    for obj in dirty:
        obj.save()
    return filled, failed


# ─────────────────────────────────────────────
# Survey
# ─────────────────────────────────────────────

class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    form = QuestionInlineForm
    extra = 0
    show_change_link = True  # 選項與其他語言在題目自己的頁面編輯（Django 不支援巢狀 inline）
    fields = ("order", "qtype", "required", "text_en", "text_zh", "choice_count")
    readonly_fields = ("choice_count",)

    @admin.display(description="選項數")
    def choice_count(self, obj):
        if not obj.pk:
            return "—"
        return obj.choices.count() if obj.qtype != SurveyQuestion.QType.TEXT else "（文字題）"


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    form = SurveyForm
    inlines = [SurveyQuestionInline]
    list_display = ("name", "kind", "is_active", "question_count", "response_count", "missing", "results_link")
    list_filter = ("kind", "is_active")
    actions = ["fill_translations"]

    fieldsets = (
        (None, {
            "fields": ("kind", "name", "is_active"),
            "description": (
                "同一種問卷同時只能有一份啟用中。<b>已經有人回答的題目與選項刪不掉</b>：要改題目，"
                "請停用這一份、再新增一份，舊的回答才不會被改掉意思。<br>"
                "全站問卷只在 beta 期間（BETA_MODE=1）對外顯示。"
            ),
        }),
        ("標題", {"fields": _lang_fields("title")}),
        ("開頭說明", {"fields": _lang_fields("intro"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _q=Count("questions", distinct=True), _r=Count("responses", distinct=True),
        )

    @admin.display(description="題數", ordering="_q")
    def question_count(self, obj):
        return obj._q

    @admin.display(description="回答數", ordering="_r")
    def response_count(self, obj):
        return obj._r

    @admin.display(description="缺翻譯")
    def missing(self, obj):
        texts = [obj.title] + [q.text for q in obj.questions.all()] + [
            c.text for c in SurveyChoice.objects.filter(question__survey=obj)
        ]
        n = sum(len(missing_langs(t)) for t in texts if t)
        return f"{n} 格" if n else "—"

    @admin.display(description="結果")
    def results_link(self, obj):
        url = reverse("admin:feedback_survey_results", args=[obj.pk])
        return format_html('<a href="{}">📊 看結果</a>', url)

    @admin.action(description="🌐 用 DeepL 補齊缺的語言（標題、題目、選項）")
    def fill_translations(self, request, queryset):
        targets = []
        for survey in queryset:
            targets += [(survey, "title"), (survey, "intro")]
            for q in survey.questions.all():
                targets.append((q, "text"))
                targets += [(c, "text") for c in q.choices.all()]
        try:
            filled, failed = _fill_missing_langs(targets)
        except RuntimeError as e:
            self.message_user(request, f"❌ {e}", level=messages.ERROR)
            return
        level = messages.WARNING if failed else messages.SUCCESS
        self.message_user(request, f"已補 {filled} 格翻譯" + (f"，{failed} 格失敗（見 log）" if failed else ""), level=level)

    def get_urls(self):
        return [
            path(
                "<int:survey_id>/results/",
                self.admin_site.admin_view(self.results_view),
                name="feedback_survey_results",
            ),
        ] + super().get_urls()

    def results_view(self, request, survey_id):
        """每題的選項分布與文字題清單，可依 edition 篩選。"""
        survey = Survey.objects.get(pk=survey_id)
        responses = survey.responses.all()
        edition_id = request.GET.get("edition") or ""
        if edition_id:
            responses = responses.filter(edition_id=edition_id)

        total = responses.count()
        member_count = responses.exclude(member=None).count()
        answers =SurveyAnswer.objects.filter(response__in=responses)
        choice_counts = dict(
            answers.exclude(choice=None).values_list("choice").annotate(n=Count("id"))
        )

        questions = []
        for q in survey.questions.prefetch_related("choices"):
            row = {"q": q, "text": localized(q.text, ADMIN_LANG),
                   "choices": None, "answered": None, "texts": None}
            if q.qtype == SurveyQuestion.QType.TEXT:
                row["texts"] = list(
                    answers.filter(question=q)
                    .select_related("response")
                    .order_by("-response__created_at")
                    .values("text", "response__edition_name", "response__created_at", "response_id")[:200]
                )
            else:
                other_texts = {}
                for t in (answers.filter(question=q, choice__is_other=True).exclude(text="")
                          .order_by("-response__created_at")
                          .values("choice_id", "text", "response__edition_name", "response__created_at")):
                    other_texts.setdefault(t["choice_id"], []).append(t)
                answered = answers.filter(question=q).values("response").distinct().count()
                row["answered"] = answered
                row["choices"] = [
                    {
                        "text": localized(c.text, ADMIN_LANG),
                        "count": choice_counts.get(c.id, 0),
                        "pct": round(choice_counts.get(c.id, 0) / answered * 100) if answered else 0,
                        "others": other_texts.get(c.id, [])[:100],
                    }
                    for c in q.choices.all()
                ]
            questions.append(row)

        editions = (
            survey.responses.exclude(edition=None)
            .values("edition_id", "edition_name").annotate(n=Count("id")).order_by("-n")[:100]
        )

        return TemplateResponse(request, "admin/feedback/survey_results.html", {
            **self.admin_site.each_context(request),
            "title": f"問卷結果：{survey.name}",
            "opts": self.model._meta,
            "survey": survey,
            "total": total,
            "member_count": member_count,
            "anon_count": total - member_count,
            "questions": questions,
            "editions": editions,
            "edition_id": edition_id,
        })


# ─────────────────────────────────────────────
# Question（選項在這裡編輯）
# ─────────────────────────────────────────────

class SurveyChoiceInline(admin.TabularInline):
    model = SurveyChoice
    form = ChoiceForm
    extra = 3
    fields = ("order", "is_other") + _lang_fields("text")


@admin.register(SurveyQuestion)
class SurveyQuestionAdmin(admin.ModelAdmin):
    form = QuestionForm
    inlines = [SurveyChoiceInline]
    list_display = ("__str__", "survey", "order", "qtype", "required")
    list_filter = ("survey", "qtype")
    fieldsets = (
        (None, {"fields": ("survey", "order", "qtype", "required")}),
        ("題目", {"fields": _lang_fields("text")}),
    )

    def get_inlines(self, request, obj):
        # 文字題沒有選項
        if obj and obj.qtype == SurveyQuestion.QType.TEXT:
            return []
        return super().get_inlines(request, obj)


# ─────────────────────────────────────────────
# Response（唯讀）
# ─────────────────────────────────────────────

class SurveyAnswerInline(admin.TabularInline):
    model = SurveyAnswer
    extra = 0
    can_delete = False
    fields = ("question_text", "answer")
    readonly_fields = ("question_text", "answer")

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="題目")
    def question_text(self, obj):
        return localized(obj.question.text, ADMIN_LANG)

    @admin.display(description="回答")
    def answer(self, obj):
        if not obj.choice_id:
            return obj.text
        label = localized(obj.choice.text, ADMIN_LANG)
        return f"{label}：{obj.text}" if obj.text else label


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    inlines = [SurveyAnswerInline]
    list_display = ("created_at", "survey", "edition_name", "who", "page", "lang", "is_partial")
    list_filter = ("survey", "is_partial", "lang", "page")
    search_fields = ("edition_name", "answers__text")
    readonly_fields = ("survey", "edition", "edition_name", "member", "lang", "page", "created_at")
    raw_id_fields = ("edition", "member")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="填寫者")
    def who(self, obj):
        return obj.member or "（匿名）"
