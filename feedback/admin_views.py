"""
後台「回饋總覽」：把散在各處的用戶回饋依時間合併成一張只讀清單。

不搬資料、不整合表——每一列都連回原本的 admin change page，審核或處理仍在原處做。
來源：
  flowchart  流程圖建議（整張圖 / 導覽中的單一節點）  game.FlowchartSuggestion
  survey     問卷的文字題                               feedback.SurveyAnswer
  rulesbot   Rulesbot 回答的倒讚與文字說明              game.ChatMessage
  game       推薦新增桌遊                               game.GameSuggestion
  contact    聯絡表單                                   messaging.ContactInquiry

msg.Msg（/api/msg/feedback/）不列：前端已經沒有地方呼叫它。
"""

from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from feedback.models import localized

SOURCES = {
    "flowchart": "流程圖建議",
    "survey": "問卷文字題",
    "rulesbot": "Rulesbot 回答",
    "game": "推薦新增桌遊",
    "contact": "聯絡表單",
}
DAY_CHOICES = (7, 30, 90, 365)
# 每個來源最多撈這麼多筆再合併，避免某個來源量大時整頁拖慢（VPS RAM 很緊）
PER_SOURCE_LIMIT = 300


def _who(member):
    return str(member) if member else "（匿名）"


def _flowchart_rows(since):
    from game.models import FlowchartSuggestion

    qs = (FlowchartSuggestion.objects.filter(created_at__gte=since)
          .select_related("edition", "submitted_by").order_by("-created_at")[:PER_SOURCE_LIMIT])
    for s in qs:
        target = f"節點：{s.node_label or s.node_id}" if s.node_id else "整張圖"
        yield {
            "source": "flowchart",
            "at": s.created_at,
            "edition": s.edition.name if s.edition else "",
            "context": f"{s.ruleset} · {target}" if s.ruleset else target,
            "content": s.content,
            "who": _who(s.submitted_by),
            "status": s.get_status_display(),
            "url": reverse("admin:game_flowchartsuggestion_change", args=[s.pk]),
        }


def _survey_rows(since):
    from django.db.models import Q

    from feedback.models import SurveyAnswer

    qs = (SurveyAnswer.objects.filter(response__created_at__gte=since)
          .filter(Q(choice=None) | Q(choice__is_other=True))
          .exclude(text="")
          .select_related("question", "response__survey", "response__member")
          .order_by("-response__created_at")[:PER_SOURCE_LIMIT])
    for a in qs:
        r = a.response
        yield {
            "source": "survey",
            "at": r.created_at,
            "edition": r.edition_name,
            "context": f"{r.survey.name} · {localized(a.question.text, 'zh')}",
            "content": a.text,
            "who": _who(r.member),
            "status": "",
            "url": reverse("admin:feedback_surveyresponse_change", args=[r.pk]),
        }


def _rulesbot_rows(since):
    from django.db.models import Q

    from game.models import ChatMessage

    qs = (ChatMessage.objects.filter(created_at__gte=since)
          .exclude(role="user")
          .filter(Q(feedback=ChatMessage.Feedback.DISLIKE)
                  | (Q(feedback_text__isnull=False) & ~Q(feedback_text="")))
          .select_related("session__edition", "session__user")
          .order_by("-created_at")[:PER_SOURCE_LIMIT])
    for m in qs:
        edition = m.session.edition if m.session_id else None
        rating = {ChatMessage.Feedback.LIKE: "👍", ChatMessage.Feedback.DISLIKE: "👎"}.get(m.feedback, "")
        answer = (m.content or "").strip().replace("\n", " ")
        yield {
            "source": "rulesbot",
            "at": m.created_at,
            "edition": (edition.name or edition.game.canonical_name) if edition else "",
            "context": f"{rating} 回答：{answer[:80]}{'…' if len(answer) > 80 else ''}",
            "content": m.feedback_text or "（只按了倒讚，沒有文字）",
            "who": _who(m.session.user if m.session_id else None),
            "status": "",
            "url": reverse("admin:game_chatmessage_change", args=[m.pk]),
        }


def _game_rows(since):
    from game.models import GameSuggestion

    qs = (GameSuggestion.objects.filter(created_at__gte=since)
          .select_related("submitted_by").order_by("-created_at")[:PER_SOURCE_LIMIT])
    for s in qs:
        yield {
            "source": "game",
            "at": s.created_at,
            "edition": s.name,
            "context": s.rulebook_url,
            "content": s.note,
            "who": _who(s.submitted_by),
            "status": s.get_status_display(),
            "url": reverse("admin:game_gamesuggestion_change", args=[s.pk]),
        }


def _contact_rows(since):
    from messaging.models import ContactInquiry

    qs = ContactInquiry.objects.filter(created_at__gte=since).order_by("-created_at")[:PER_SOURCE_LIMIT]
    for c in qs:
        yield {
            "source": "contact",
            "at": c.created_at,
            "edition": "",
            "context": c.subject,
            "content": c.content,
            "who": f"{c.name} <{c.email}>",
            "status": "已讀" if c.is_read else "未讀",
            "url": reverse("admin:messaging_contactinquiry_change", args=[c.pk]),
        }


ROW_BUILDERS = {
    "flowchart": _flowchart_rows,
    "survey": _survey_rows,
    "rulesbot": _rulesbot_rows,
    "game": _game_rows,
    "contact": _contact_rows,
}


@staff_member_required
def feedback_inbox(request):
    try:
        days = int(request.GET.get("days", 30))
    except ValueError:
        days = 30
    if days not in DAY_CHOICES:
        days = 30
    source = request.GET.get("source", "")
    if source not in SOURCES:
        source = ""
    q = (request.GET.get("q") or "").strip()

    since = timezone.now() - timedelta(days=days)
    rows, counts = [], {}
    for key, build in ROW_BUILDERS.items():
        items = list(build(since))
        for item in items:
            item["source_label"] = SOURCES[key]
        counts[key] = len(items)
        if not source or source == key:
            rows += items

    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in f"{r['edition']} {r['context']} {r['content']}".lower()]
    rows.sort(key=lambda r: r["at"], reverse=True)

    from django.contrib import admin

    return TemplateResponse(request, "admin/feedback/inbox.html", {
        **admin.site.each_context(request),
        "title": "回饋總覽",
        "rows": rows,
        "sources": [(k, label, counts.get(k, 0)) for k, label in SOURCES.items()],
        "source": source,
        "days": days,
        "day_choices": DAY_CHOICES,
        "q": q,
        "per_source_limit": PER_SOURCE_LIMIT,
    })
