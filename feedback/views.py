"""
問卷 API。刻意不用 DRF：DRF 的 SessionAuthentication 會自己強制 CSRF，
匿名送出就做不到零 cookie。

語言參數叫 `l` 不叫 `lang`：translation.LanguageMiddleware 在 /api/ 底下看到
?lang= 會寫進 session，匿名訪客就因此拿到 session cookie。

錯誤一律回代碼（errors: {question_id: code}），訊息文字由前端的 partial 用
{% t %} 渲染好帶著，API 不必查翻譯。
"""

import json
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from feedback.models import (
    FALLBACK_LANG, LANG_CODES, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse, localized,
)
from feedback.security import (
    MEMBER_SUBMISSIONS_PER_HOUR, anon_quota_exceeded, check_token, csrf_if_authenticated,
    is_duplicate_submission, is_honeypot_filled, issue_token, token_overused,
)
from member.beta import is_beta

TEXT_MAX_LENGTH = 2000
PAGE_MAX_LENGTH = 200

# 題目內容的快取。admin 存檔時 bump 版本號（見 signals.py），舊 key 自然失效。
CACHE_VERSION_KEY = "feedback:survey:version"
CACHE_TIMEOUT = 60 * 60


def _lang(value):
    return value if value in LANG_CODES else FALLBACK_LANG


def _member(request):
    return getattr(request.user, "member", None) if request.user.is_authenticated else None


def _active_survey(kind):
    """目前開放中的問卷；site 問卷只在 beta 期間開放，關掉 beta 就自動收起來。"""
    if kind == Survey.Kind.SITE and not is_beta():
        return None
    return Survey.objects.filter(kind=kind, is_active=True).first()


def _edition(kind, raw_id):
    """
    edition 問卷必須指定 edition，site 問卷一律不掛 edition。
    回傳 (edition, ok)。
    """
    if kind != Survey.Kind.EDITION:
        return None, True
    from game.models import Edition
    try:
        edition_id = uuid.UUID(str(raw_id))
    except (TypeError, ValueError):
        return None, False
    edition = Edition.objects.select_related("game").filter(id=edition_id).first()
    return edition, edition is not None


def _survey_payload(survey, lang):
    version = cache.get(CACHE_VERSION_KEY, 0)
    key = f"feedback:survey:{survey.id}:{lang}:{version}"
    payload = cache.get(key)
    if payload is not None:
        return payload

    questions = survey.questions.prefetch_related("choices")
    payload = {
        "id": survey.id,
        "title": localized(survey.title, lang),
        "intro": localized(survey.intro, lang),
        "questions": [
            {
                "id": q.id,
                "type": q.qtype,
                "required": q.required,
                "text": localized(q.text, lang),
                "choices": [
                    {"id": c.id, "text": localized(c.text, lang), "other": c.is_other}
                    for c in q.choices.all()
                ],
            }
            for q in questions
        ],
    }
    cache.set(key, payload, CACHE_TIMEOUT)
    return payload


class SurveyView(View):
    """GET /api/feedback/surveys/<kind>/?edition=<uuid>&l=<lang>"""

    def get(self, request, kind):
        if kind not in Survey.Kind.values:
            return JsonResponse({"error": "unknown_kind"}, status=404)

        survey = _active_survey(kind)
        if survey is None or not survey.questions.exists():
            # 沒有開放中的問卷：前端不顯示浮動按鈕
            return HttpResponse(status=204)

        edition, ok = _edition(kind, request.GET.get("edition"))
        if not ok:
            return JsonResponse({"error": "edition_required"}, status=400)

        response = JsonResponse({
            "token": issue_token(survey.id),   # 每次都重發，不能放進上面的快取
            "survey": _survey_payload(survey, _lang(request.GET.get("l"))),
        })
        response["Cache-Control"] = "private, no-store"
        return response


def _parse_answers(questions, raw_answers, raw_others=None, partial=False):
    """
    驗證前端送來的 {question_id: value}，回傳 (要建立的 SurveyAnswer 清單, errors)。

    value 的形狀依題型：single → 選項 id、multi → 選項 id 的陣列、text → 字串。
    未回答的選填題直接略過，不存空列。partial＝使用者中途離開，必填題也允許缺漏。
    """
    if not isinstance(raw_answers, dict):
        raw_answers = {}
    if not isinstance(raw_others, dict):
        raw_others = {}   # {選項 id: 「其他」填的字}

    answers, errors = [], {}
    for q in questions:
        raw = raw_answers.get(str(q.id))
        valid_choices = {c.id: c for c in q.choices.all()}

        if q.qtype == SurveyQuestion.QType.TEXT:
            text = (raw or "").strip() if isinstance(raw, str) else ""
            if len(text) > TEXT_MAX_LENGTH:
                errors[q.id] = "too_long"
            elif text:
                answers.append(SurveyAnswer(question=q, text=text))
            elif q.required and not partial:
                errors[q.id] = "required"
            continue

        picked = raw if isinstance(raw, list) else ([] if raw in (None, "") else [raw])
        if q.qtype == SurveyQuestion.QType.SINGLE and len(picked) > 1:
            errors[q.id] = "invalid_choice"
            continue
        try:
            picked_ids = list(dict.fromkeys(int(v) for v in picked))
        except (TypeError, ValueError):
            errors[q.id] = "invalid_choice"
            continue
        if any(cid not in valid_choices for cid in picked_ids):
            errors[q.id] = "invalid_choice"
        elif not picked_ids:
            if q.required and not partial:
                errors[q.id] = "required"
        else:
            for cid in picked_ids:
                choice = valid_choices[cid]
                other = ""
                if choice.is_other:
                    other = raw_others.get(str(cid))
                    other = other.strip() if isinstance(other, str) else ""
                    if len(other) > TEXT_MAX_LENGTH:
                        errors[q.id] = "too_long"
                answers.append(SurveyAnswer(question=q, choice=choice, text=other))

    return answers, errors


@method_decorator(csrf_if_authenticated, name="dispatch")
class SurveyResponseCreateView(View):
    """POST /api/feedback/surveys/<survey_id>/responses/"""

    def post(self, request, survey_id):
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "bad_request"}, status=400)
        if not isinstance(payload, dict):
            return JsonResponse({"success": False, "error": "bad_request"}, status=400)

        if is_honeypot_filled(payload):
            # 假裝成功，不讓機器人知道被擋
            return JsonResponse({"success": True})

        survey = Survey.objects.filter(id=survey_id).first()
        if survey is None or _active_survey(survey.kind) != survey:
            # 問卷剛被停用、或 beta 已結束：前端當作「不必再顯示」
            return JsonResponse({"success": False, "error": "closed"}, status=410)

        edition, ok = _edition(survey.kind, payload.get("edition_id"))
        if not ok:
            return JsonResponse({"success": False, "error": "edition_required"}, status=400)

        # 簽章 token：沒有、簽章不對、或送得比真人快 → 跟 honeypot 一樣假裝成功
        token = payload.get("token")
        verdict = check_token(token, survey.id)
        if verdict in ("invalid", "too_fast"):
            return JsonResponse({"success": True})
        if verdict == "expired":
            return JsonResponse({"success": False, "error": "expired"}, status=400)
        if token_overused(token):
            return JsonResponse({"success": False, "error": "busy"}, status=429)

        member = _member(request)
        if member is None:
            if anon_quota_exceeded():
                return JsonResponse({"success": False, "error": "busy"}, status=429)
        elif SurveyResponse.objects.filter(
            member=member, created_at__gte=timezone.now() - timedelta(hours=1),
        ).count() >= MEMBER_SUBMISSIONS_PER_HOUR:
            return JsonResponse({"success": False, "error": "busy"}, status=429)

        fingerprint = json.dumps(
            [survey.id, str(edition.id) if edition else "", member.pk if member else None,
             payload.get("answers"), payload.get("others")],
            sort_keys=True, default=str,
        )
        if is_duplicate_submission(fingerprint):
            return JsonResponse({"success": True})

        questions = list(survey.questions.prefetch_related("choices"))
        partial = payload.get("partial") is True
        answers, errors = _parse_answers(questions, payload.get("answers"), payload.get("others"), partial=partial)
        if errors:
            return JsonResponse({"success": False, "errors": errors}, status=400)
        if not answers:
            return JsonResponse({"success": False, "error": "empty"}, status=400)

        edition_name = ""
        if edition is not None:
            edition_name = edition.name or (edition.game.canonical_name if edition.game_id else "")

        with transaction.atomic():
            response = SurveyResponse.objects.create(
                survey=survey,
                edition=edition,
                edition_name=edition_name[:300],
                member=member,
                lang=_lang(payload.get("lang")),
                page=str(payload.get("page") or "")[:PAGE_MAX_LENGTH],
                is_partial=partial,
            )
            for a in answers:
                a.response = response
            SurveyAnswer.objects.bulk_create(answers)

        return JsonResponse({"success": True})
