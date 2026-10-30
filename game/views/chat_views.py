# game/views/chat_views.py
from django.shortcuts import render, get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from game.models import Rulebook, ChatSession, ChatMessage
from game.rag.rag_service import get_rag_service
from game.selectors import resolve_chat_bundle
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

import logging
logger = logging.getLogger(__name__)

from game.rag.throttling import ChatSustainedThrottle

# API：/api/game/edition/<uuid>/chat/
def _eligible_rulebooks(mode):
    """
    可用來回答的 Rulebook：兩種模式的「準備好了」定義不同。
    rag   -> 至少有一筆 RulebookNode（已 chunk 並索引）
    whole -> whole_context 非空即可（不需要 chunk / Qdrant）
    """
    if mode == "whole":
        return Rulebook.objects.exclude(whole_context="")
    return Rulebook.objects.filter(nodes__isnull=False).distinct()


UNLIMITED = {"remaining": -1, "total": -1, "reset_time": None}


def get_chat_limits(user, edition_id=None):
    """這位使用者在這款 edition 上還剩幾次提問。total == -1 代表無限。

    無限的三種人：
      1. staff / superuser
      2. tier prompt_per_week == -1 的會員
      3. **對這一款 edition 有永久解鎖的會員**（member.EditionUnlock，免費名額
         或 US$1 加購；與 tier 脫鉤，訂閱過期降級也還在）

    第 3 種是 per-edition 的，所以呼叫端一定要把 edition_id 帶進來。
    edition_id 留預設 None 是為了讓漏改的呼叫端退回舊的全域行為，而不是炸掉
    ——但那會讓已解鎖的使用者被錯誤地計入配額，新增呼叫端時請務必帶上。

    已解鎖 edition 的訊息也不計入每週用量（見下方 exclude）：「無限」如果還
    會侵蝕其他 edition 的免費配額，等於在別處把額度用光，那不是無限。

    注意這裡只管每週配額。防濫用的每日硬上限是另一層（rag/throttling.py 的
    ChatSustainedThrottle），解鎖不會豁免它。
    """
    # staff / superuser 一律視為無限，不受 tier prompt_per_week 限制
    if user.is_staff or user.is_superuser:
        return dict(UNLIMITED)

    member = getattr(user, 'member', None)

    # 兩個查詢各自 try：合在一起的話，解鎖查詢出問題會把已經算對的 limit_val
    # 一起打回 -1（＝無聲的無限額度），那是最糟的失敗方向。
    try:
        limit_val = member.limit('prompt_per_week') if member else -1
    except Exception as e:
        logger.error(f"Error getting prompt_per_week limit: {e}")
        limit_val = -1

    unlocked_ids = set()
    if member is not None:
        try:
            unlocked_ids = member.unlocked_edition_ids()
        except Exception as e:
            # 讀不到解鎖就當作沒有：配額照算，使用者頂多被誤計一次，
            # 比反過來白送無限額度安全。
            logger.error(f"Error getting edition unlocks: {e}")

    if limit_val == -1:
        return dict(UNLIMITED)

    # 這一款已永久解鎖 → 這一頁的問答不設每週上限
    if member is not None and member.has_unlocked(edition_id):
        return dict(UNLIMITED)

    now = timezone.now()
    week_ago = now - timedelta(days=7)

    counted = ChatMessage.objects.filter(
        session__user=user,
        role="user",
        created_at__gte=week_ago,
    )
    if unlocked_ids:
        # ChatSession.edition 可為 NULL，而 NOT (col IN (...)) 在 SQL 裡會把
        # NULL 列一起濾掉。明寫 OR IS NULL，不倚賴 exclude() 的 NULL 處理細節
        # ——少算配額是對使用者有利的方向，但那會變成無聲的免費額度。
        counted = counted.filter(
            Q(session__edition_id__isnull=True)
            | ~Q(session__edition_id__in=unlocked_ids)
        )

    used = counted.count()

    remaining = max(0, limit_val - used)
    reset_time = None

    if remaining <= 0:
        oldest = counted.order_by("created_at").first()
        if oldest:
            reset_time = (oldest.created_at + timedelta(days=7)).isoformat()

    return {
        "remaining": remaining,
        "total": limit_val,
        "reset_time": reset_time
    }

class ChatView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == 'POST':
            return [ChatSustainedThrottle()]
        return []

    def get(self, request, edition_id):
        # 找該用戶最近一次對該 Edition 的對話（已清除的 session 是 soft delete，
        # 排除掉才不會讓使用者又看到「已清除」的歷史）
        session = ChatSession.objects.filter(
            edition_id=edition_id,
            user=request.user,
            deleted_at__isnull=True,
        ).order_by("-created_at").first()
        
        limits = get_chat_limits(request.user, edition_id)

        if not session:
            return Response({"session_id": None, "messages": [], "limits": limits})
            
        messages = session.messages.order_by("created_at")
        history = []
        for m in messages:
            history.append({
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "sources": m.sources,
                "feedback": m.feedback,
                "feedback_text": m.feedback_text,
                "mode": m.mode,
                "category": m.category,
            })
            
        return Response({
            "session_id": str(session.id),
            "messages": history,
            "limits": limits
        })

    def post(self, request, edition_id):
        from game.models import Edition
        edition = get_object_or_404(Edition, pk=edition_id)

        # 0a. 決定問答路徑。
        # 所有人（含一般用戶）預設走 whole-context + 分類路由；RAG 已停用，
        # 只有 staff 明確指定 mode=rag 才會走那條舊路徑（保留供對照）。
        # force_provider 同樣只有 staff 能指定，用來蓋過分類器選的主模型。
        is_staff = request.user.is_staff or request.user.is_superuser
        requested_mode = request.data.get("mode")
        mode = "rag" if (requested_mode == "rag" and is_staff) else "whole"

        force_provider = request.data.get("provider") if is_staff else None
        if force_provider not in ("gemini", "claude"):
            force_provider = None

        # 0b. Check Limits
        limits = get_chat_limits(request.user, edition_id)
        if limits["total"] != -1 and limits["remaining"] <= 0:
            return Response({
                "error": "Prompt limit reached.",
                "limits": limits
            }, status=429)

        # 1. 取得 / 建立 session
        session_id = request.data.get("session_id")
        session = None
        
        if session_id:
            try:
                # 排除已清除的 session：前端在清除成功後會把自己的 sessionId 重設成
                # null，正常流程不會走到這裡；這裡是防呆，避免舊分頁殘留的
                # session_id 讓「已清除」的對話又被接續下去。
                session = ChatSession.objects.get(
                    pk=session_id, user=request.user, deleted_at__isnull=True,
                )
            except ChatSession.DoesNotExist:
                session = None

        if not session:
            # 優先找該用戶最近一次對該 Edition 的對話
            session = ChatSession.objects.filter(
                edition=edition,
                user=request.user,
                deleted_at__isnull=True,
            ).order_by("-created_at").first()
            
            if not session:
                # 建立新 Session (Rulebook 暫時為空，稍後補上最近一次使用的)
                session = ChatSession.objects.create(
                    edition=edition, 
                    user=request.user,
                    user_name=request.user.username
                )

        # 2. 決定要用哪些 Rulebook 當作答題依據
        #
        # whole 模式打包的是「一個 edition + 一種語言」底下的全部就緒規則書
        # （主規則書 + 擴充 + FAQ 一起進 prompt），語言與 edition 的 fallback
        # 都在 selectors.resolve_chat_bundle 裡，不要在這裡另外寫一份。
        #
        # rag 模式（staff 專用）維持單本：向量檢索是 rulebook_id 過濾的，
        # 一次跨多本沒有對應的實作。
        if mode == "whole":
            # /api/ 沒有語言網址前綴，request.lang 來自 ?lang= → session → 預設
            # （見 translation/middleware.py 的 LanguageMiddleware）。前端會在
            # chat API 的網址帶上頁面語言，session 為空時才不會一律退成英文。
            lang_code = request.data.get("lang") or getattr(request, "lang", "en")
            bundle = resolve_chat_bundle(edition, lang_code)
            target_rulebooks = bundle.rulebooks
        else:
            indexed_rulebooks = _eligible_rulebooks(mode)
            target_rulebook = None

            # 前端傳入的 explicit rulebook_id（whole 模式打包後指定單本沒有意義，
            # 所以只有 rag 模式看這個參數）
            req_rulebook_id = request.data.get("rulebook_id")
            if req_rulebook_id:
                target_rulebook = indexed_rulebooks.filter(pk=req_rulebook_id).first()

            # Session 紀錄的最後一本（仍就緒才沿用）-> 保持對話連貫性
            if not target_rulebook and session.rulebook_id:
                target_rulebook = indexed_rulebooks.filter(pk=session.rulebook_id).first()
                if not target_rulebook:
                    # Stale pointer to a rulebook that isn't ready for this mode; auto-heal
                    logger.warning(
                        f"Session {session.id} pointed to rulebook {session.rulebook_id} "
                        f"which is not ready for mode={mode}; clearing to re-pick."
                    )
                    session.rulebook = None

            if not target_rulebook:
                target_rulebook = indexed_rulebooks.filter(edition=edition).first()
                if not target_rulebook:
                    target_rulebook = indexed_rulebooks.filter(
                        edition__game=edition.game,
                    ).first()

            target_rulebooks = [target_rulebook] if target_rulebook else []

        if not target_rulebooks:
             return Response({"error": "No rulebook available for this game."}, status=400)

        # Session 的 rulebook 欄位是單值，存打包的第一本當代表。打包內容每次請求
        # 都依當下的介面語言重算，所以這個指標只用來標示「這場對話在聊哪一款」，
        # 不參與 whole 模式的選書。
        primary_rulebook = target_rulebooks[0]
        if session.rulebook_id != primary_rulebook.id:
            session.rulebook = primary_rulebook
            session.save(update_fields=['rulebook', 'updated_at'])

        # 3. 取用戶輸入
        question = request.data.get("message", "").strip()
        if not question:
            return Response({"error": "message is required"}, status=400)

        # 4. 撈最近 6 則歷史（3 組完整問答；取偶數才不會以 AI 回答開頭、
        #    看不到對應的提問而形成斷頭上下文）
        history_qs = session.messages.order_by("-created_at")[:6]
        history = [
            {"role": m.role, "content": m.content}
            for m in reversed(history_qs)
        ]

        # 5. 呼叫問答服務
        rag_service = get_rag_service()
        category = ""
        try:
            if mode == "whole":
                # 分類決定要走哪條 provider 鏈；刻意不帶對話歷史（判準是這句話
                # 本身，帶歷史反而會污染判斷）。classify_question 內部已吞掉例外，
                # 失敗一律回 "other"，不會擋住答題。
                category = rag_service.classify_question(question)
                result = rag_service.answer_question_whole(
                    question=question,
                    rulebook_ids=[str(rb.id) for rb in target_rulebooks],
                    history=history,
                    category=category,
                    force_provider=force_provider,
                )
            else:
                result = rag_service.answer_question(
                    question=question,
                    rulebook_id=str(primary_rulebook.id), # Use the resolved rulebook
                    history=history,
                )
        except Exception as e:
            logger.error(f"RAG service error (mode={mode}): {e}")
            return Response(
                {"error": "The AI provider is currently experiencing high demand or is temporarily unavailable. Please try again later."},
                status=503
            )

        # 6. 寫入 DB
        ChatMessage.objects.create(
            session=session, role="user", content=question,
            category=category, mode=mode,
        )

        prompt_tokens = result.metadata.get("prompt_tokens")
        completion_tokens = result.metadata.get("completion_tokens")
        total_tokens = result.metadata.get("total_tokens")
        cached_tokens = result.metadata.get("cached_tokens")
        
        assistant_msg = ChatMessage.objects.create(
            session=session,
            role=result.model or "Gemini",
            content=result.answer,
            sources=result.sources,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            category=category,
            mode=mode,
        )

        # 7. 回傳
        return Response(
            {
                "session_id": str(session.id),
                "message_id": str(assistant_msg.id),
                "answer": result.answer,
                "model": assistant_msg.role,
                "sources": result.sources,
                "figures": result.figures,
                "debug": result.metadata,
                "mode": mode,
                "category": category,
                # used_rulebook 保留單值給既有的 App 用戶端；新的多本資訊走
                # used_rulebooks，順序與答案裡的 Ref 1/2/3 編號一致。
                "used_rulebook": {
                    "id": str(primary_rulebook.id),
                    "title": primary_rulebook.title
                },
                "used_rulebooks": [
                    {"index": i, "id": str(rb.id), "title": rb.title}
                    for i, rb in enumerate(target_rulebooks, start=1)
                ],
                "limits": get_chat_limits(request.user, edition_id)
            },
            status=status.HTTP_200_OK,
        )

class MessageFeedbackView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        logger.info(f"Received feedback for message {message_id}. Data: {request.data}")
        message = get_object_or_404(ChatMessage, pk=message_id)
        
        # 確保訊息屬於該用戶（透過 session）
        if message.session.user != request.user:
            logger.warning(f"Unauthorized feedback attempt for message {message_id} by user {request.user}")
            return Response({"error": "Unauthorized"}, status=403)
            
        feedback_value = request.data.get("feedback")
        feedback_text = request.data.get("feedback_text", "").strip()
        
        if feedback_value is not None:
            try:
                feedback_value = int(feedback_value)
                if feedback_value not in ChatMessage.Feedback.values:
                    return Response({"error": "Invalid feedback value"}, status=400)
                message.feedback = feedback_value
            except (ValueError, TypeError):
                return Response({"error": "Invalid feedback type"}, status=400)
                
        if feedback_text is not None:
            message.feedback_text = feedback_text
            
        message.save()
        logger.info(f"Feedback saved for message {message_id}. Feedback: {message.feedback}, Text: {message.feedback_text}")
        
        return Response({"status": "ok"})


class ClearChatView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, edition_id):
        # 「清除」是 soft delete：session 與訊息都留在 DB（mode/category/token
        # 統計才不會被使用者的清除動作侵蝕），只是打上 deleted_at 時間戳，
        # 從使用者可見的歷史與「接續對話」邏輯裡濾掉（見 ChatView.get/post）。
        sessions = ChatSession.objects.filter(
            edition_id=edition_id,
            user=request.user,
            deleted_at__isnull=True,
        )

        message_count = ChatMessage.objects.filter(session__in=sessions).count()
        session_count = sessions.count()
        sessions.update(deleted_at=timezone.now())

        return Response({
            "status": "ok",
            "deleted_sessions": session_count,
            "deleted_messages": message_count
        })


class CollectionAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from interaction.models import Interaction
        from django.db import models as db_models

        all_statuses = ["past", "owned", "wish"]
        all_ratings = ["amazing", "nice", "nah", "nightmare"]
        status_filter = request.GET.getlist("status") or all_statuses
        rating_filter = request.GET.getlist("rating") or all_ratings

        interactions = Interaction.objects.filter(
            member=request.user.member,
            status__in=status_filter,
        ).select_related("edition")

        if set(rating_filter) != set(all_ratings):
            interactions = interactions.filter(
                db_models.Q(rating__in=rating_filter) | db_models.Q(rating__isnull=True)
            )

        interactions = interactions.order_by("-updated_at")

        data = [
            {
                "id": str(i.id),
                "edition_id": str(i.edition.id),
                "edition_name": i.edition.name,
                "edition_thumbnail": i.edition.thumbnail.url if i.edition.thumbnail else None,
                "status": i.status,
                "rating": i.rating,
            }
            for i in interactions
        ]
        return Response(data)


class InteractionAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, edition_id):
        from interaction.models import Interaction
        from game.models import Edition
        edition = get_object_or_404(Edition, id=edition_id)
        try:
            interaction = Interaction.objects.get(member=request.user.member, edition=edition)
            return Response({"status": interaction.status, "rating": interaction.rating})
        except Interaction.DoesNotExist:
            return Response({"status": None, "rating": None})

    def post(self, request, edition_id):
        from interaction.models import Interaction
        from game.models import Edition
        edition = get_object_or_404(Edition, id=edition_id)

        interaction, _ = Interaction.objects.get_or_create(
            member=request.user.member,
            edition=edition,
        )

        data = request.data
        if "rating" in data:
            val = data.get("rating")
            interaction.rating = val if val else None
        if "status" in data:
            val = data.get("status")
            interaction.status = val if val else None

        interaction.save()
        return Response({"status": interaction.status, "rating": interaction.rating})