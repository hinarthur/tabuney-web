"""
問卷與回饋的數據聚合。

跟 game/reports.py、stats/reports.py 同一個慣例：不依賴 request 的純函式，由
admin 首頁的 AdminStatsView 呼叫。
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone


def survey_insights(days=30, limit=10):
    """
    各問卷近 N 天的回答數、會員與匿名的比例，以及填寫最多的 edition。

    匿名回答不記任何識別碼，同一人可能填過不只一次，所以匿名數是「份數」不是人數。
    """
    from feedback.models import Survey, SurveyAnswer, SurveyResponse, localized

    since = timezone.now() - timedelta(days=days)
    responses = SurveyResponse.objects.filter(created_at__gte=since)

    total = responses.count()
    members = responses.exclude(member=None).count()

    surveys = [
        {
            "name": s.name,
            "kind": s.get_kind_display(),
            "is_active": s.is_active,
            "responses": s.n,
            "partial": s.p,
        }
        for s in Survey.objects.annotate(
            n=Count("responses", filter=Q(responses__created_at__gte=since)),
            p=Count("responses", filter=Q(responses__created_at__gte=since, responses__is_partial=True)),
        ).filter(Q(is_active=True) | Q(n__gt=0)).order_by("-is_active", "-n")
    ]

    top_editions = [
        {"edition": r["edition_name"] or "(已刪除)", "total": r["total"]}
        for r in responses.exclude(edition=None)
        .values("edition_name").annotate(total=Count("id")).order_by("-total")[:limit]
    ]

    partial = responses.filter(is_partial=True).count()

    # 每天的份數（補 0，圖才連續）
    per_day = {
        r["d"]: r["n"]
        for r in responses.annotate(d=TruncDate("created_at")).values("d").annotate(n=Count("id"))
    }
    today = timezone.localdate()
    daily = [
        {"date": (today - timedelta(days=i)).isoformat(),
         "count": per_day.get(today - timedelta(days=i), 0)}
        for i in range(days - 1, -1, -1)
    ]

    by_page = [
        {"page": r["page"] or "(未記錄)", "total": r["total"]}
        for r in responses.values("page").annotate(total=Count("id")).order_by("-total")[:limit]
    ]
    by_lang = [
        {"lang": r["lang"] or "-", "total": r["total"]}
        for r in responses.values("lang").annotate(total=Count("id")).order_by("-total")
    ]

    # 啟用中問卷的每題分布（選項次數／文字題回答數）
    questions = []
    for survey in Survey.objects.filter(is_active=True):
        answers = SurveyAnswer.objects.filter(response__in=responses.filter(survey=survey))
        choice_counts = dict(
            answers.exclude(choice=None).values_list("choice").annotate(n=Count("id"))
        )
        for q in survey.questions.prefetch_related("choices"):
            row = {"survey": survey.name, "text": localized(q.text, "zh") or localized(q.text, "en"),
                   "type": q.qtype, "choices": [], "answered": 0}
            row["answered"] = answers.filter(question=q).values("response").distinct().count()
            if q.qtype == "text":
                row["answered"] = answers.filter(question=q).exclude(text="").count()
            else:
                row["choices"] = [
                    {
                        "text": localized(c.text, "zh") or localized(c.text, "en"),
                        "count": choice_counts.get(c.id, 0),
                        "pct": round(choice_counts.get(c.id, 0) * 100 / row["answered"])
                        if row["answered"] else 0,
                    }
                    for c in q.choices.all()
                ]
            questions.append(row)

    return {
        "summary": {
            "days": days,
            "responses": total,
            "completed": total - partial,
            "partial": partial,
            "members": members,
            "anon": total - members,
            "text_answers": SurveyAnswer.objects.filter(
                Q(choice=None) | Q(choice__is_other=True), response__created_at__gte=since
            ).exclude(text="").count(),
        },
        "surveys": surveys,
        "top_editions": top_editions,
        "daily": daily,
        "by_page": by_page,
        "by_lang": by_lang,
        "questions": questions,
    }


def recent_feedback_count(days=7):
    """
    近 N 天的文字回饋總數，給待辦色塊用：數字 > 0 就該去回饋總覽看一眼。

    只算有文字內容的（流程圖建議、問卷文字題、Rulesbot 的文字說明、聯絡表單），
    單純的讚／倒讚與選擇題不算。
    """
    from feedback.models import SurveyAnswer
    from game.models import ChatMessage, FlowchartSuggestion
    from messaging.models import ContactInquiry

    since = timezone.now() - timedelta(days=days)
    return (
        FlowchartSuggestion.objects.filter(created_at__gte=since).count()
        + SurveyAnswer.objects.filter(response__created_at__gte=since, choice=None)
        .exclude(text="").count()
        + ChatMessage.objects.filter(created_at__gte=since, feedback_text__isnull=False)
        .exclude(feedback_text="").count()
        + ContactInquiry.objects.filter(created_at__gte=since).count()
    )
