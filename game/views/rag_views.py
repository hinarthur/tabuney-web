# game/views/rag_views.py
"""
RAG API Views
"""
import html as _html
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated  # 或 AllowAny
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter

from rest_framework.permissions import BasePermission
from game.models import Rulebook, RulebookFlowchart, RulebookScript
from game.rag.rag_service import get_rag_service
from game.rag.flowchart import get_flowchart_service
from game.rag.flowchart.service import FlowchartGenerationError
from game.serializers.rag_serializers import (
    QARequestSerializer,
    QAResponseSerializer,
    QADebugResponseSerializer,
    FlowchartQueryParamsSerializer,
    FlowchartResponseSerializer,
    ScriptResponseSerializer,
)

logger = logging.getLogger(__name__)


class RulebookQAView(APIView):
    """
    規則書問答 API
    
    POST /api/rulebooks/{rulebook_id}/qa/
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        summary="規則書問答",
        description="根據規則書內容回答問題（RAG）",
        request=QARequestSerializer,
        responses={200: QAResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="rulebook_id",
                location=OpenApiParameter.PATH,
                description="規則書 UUID",
                required=True,
                type=str,
            ),
            OpenApiParameter(
                name="debug",
                location=OpenApiParameter.QUERY,
                description="是否返回 debug 資訊",
                required=False,
                type=bool,
            ),
        ]
    )
    def post(self, request, rulebook_id):
        # 驗證 rulebook 存在
        rulebook = get_object_or_404(Rulebook, pk=rulebook_id)
        
        # 驗證請求
        serializer = QARequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        data = serializer.validated_data
        debug_mode = request.query_params.get("debug", "").lower() == "true"
        
        try:
            # 呼叫 RAG service
            rag_service = get_rag_service()
            result = rag_service.answer_question(
                question=data["question"],
                rulebook_id=str(rulebook_id),
                edition_id=str(rulebook.edition_id) if hasattr(rulebook, 'edition_id') else None,
                top_k=data.get("top_k", 8),
                category_filter=data.get("category") or None,
            )
            
            # 組合回應
            response_data = {
                "answer": result.answer,
                "sources": result.sources,
                "metadata": result.metadata,
            }
            
            if debug_mode:
                response_data["retrieved_chunks"] = result.retrieved_chunks
                response_serializer = QADebugResponseSerializer(response_data)
            else:
                response_serializer = QAResponseSerializer(response_data)
            
            return Response(response_serializer.data)
            
        except Exception as e:
            logger.exception(f"RAG error for rulebook {rulebook_id}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CanViewFlowchartDraft(BasePermission):
    """流程圖草稿（含未發布、付費圖）只給有 view 權限的後台人員看。"""

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.has_perm("game.view_rulebookflowchart")
        )


class CanEditFlowchart(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.has_perm("game.change_rulebookflowchart")
        )


class RulebookFlowchartView(APIView):
    """
    規則書 game-flow 流程圖 API（後台用，回傳的是草稿，不是公開版）

    GET /api/rulebooks/{rulebook_id}/flowchart/
        ?scope=lifecycle|sequence
        &strategy=structured|hybrid
        &ruleset=basic
        &edition_id=<uuid>
        &regenerate=true|false

    回傳 Mermaid 文字 + 中介 JSON。四種組合（2 scope × 2 strategy）各自快取。
    讀現有的圖需要 view 權限；觸發生成（快取不存在或 regenerate）需要 change 權限。
    """
    permission_classes = [CanViewFlowchartDraft]

    @extend_schema(
        summary="規則書遊戲流程圖",
        description="從規則書內容生成 Mermaid 桌遊流程圖（detail: concise / detailed）",
        responses={200: FlowchartResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="rulebook_id", location=OpenApiParameter.PATH,
                description="規則書 UUID", required=True, type=str,
            ),
            OpenApiParameter(
                name="detail", location=OpenApiParameter.QUERY,
                description="concise (~7-12 nodes) 或 detailed (~25-40 nodes)",
                required=False, type=str,
            ),
            OpenApiParameter(
                name="ruleset", location=OpenApiParameter.QUERY,
                description="變體名稱（預設 'basic'）",
                required=False, type=str,
            ),
            OpenApiParameter(
                name="edition_id", location=OpenApiParameter.QUERY,
                description="可選 edition UUID",
                required=False, type=str,
            ),
            OpenApiParameter(
                name="regenerate", location=OpenApiParameter.QUERY,
                description="忽略快取重新產生",
                required=False, type=bool,
            ),
            OpenApiParameter(
                name="render", location=OpenApiParameter.QUERY,
                description="json (預設) / reactflow (standalone HTML viewer)",
                required=False, type=str,
            ),
        ],
    )
    def get(self, request, rulebook_id):
        rulebook = get_object_or_404(Rulebook, pk=rulebook_id)

        params = FlowchartQueryParamsSerializer(data=request.query_params)
        if not params.is_valid():
            return Response(params.errors, status=status.HTTP_400_BAD_REQUEST)
        p = params.validated_data

        edition_id = p.get("edition_id") or getattr(rulebook, "edition_id", None)

        if not request.user.has_perm("game.change_rulebookflowchart"):
            # 只能看：不得觸發 LLM 生成（花錢，且 regenerate 會洗掉人工調整）
            if p["regenerate"]:
                return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
            obj = RulebookFlowchart.objects.filter(
                rulebook_id=rulebook_id, ruleset=p["ruleset"],
            ).first()
            if obj is None or not obj.effective_json:
                return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)
            return self._respond(rulebook, obj, True, p)

        try:
            service = get_flowchart_service()
            obj, cached = service.get_or_generate(
                rulebook_id=str(rulebook_id),
                edition_id=str(edition_id) if edition_id else None,
                ruleset=p["ruleset"],
                detail=p["detail"],
                regenerate=p["regenerate"],
            )
        except FlowchartGenerationError as e:
            msg = str(e)
            err_code = "insufficient_rulebook_structure" if "insufficient" in msg else "generation_failed"
            return Response(
                {"error": err_code, "detail": msg},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception as e:
            logger.exception(f"Flowchart error for rulebook {rulebook_id}")
            return Response(
                {"error": "internal_error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return self._respond(rulebook, obj, cached, p)

    def _respond(self, rulebook, obj, cached, p):
        fmt = p.get("render", "json")
        if fmt == "reactflow":
            title = f"{rulebook.title} — {p['detail']}"
            return HttpResponse(
                _render_react_flow_html(title, obj),
                content_type="text/html; charset=utf-8",
            )

        effective_rf = obj.adjusted_json if obj.adjusted_json else obj.react_flow_json
        payload = {
            "json": obj.intermediate_json,
            "react_flow": effective_rf,
            "is_adjusted": bool(obj.adjusted_json),
            "source_chunks": obj.source_chunk_ids or [],
            "cached": cached,
            "generated_at": obj.updated_at,
            "llm_model": obj.llm_model,
            "prompt_version": obj.prompt_version,
        }
        return Response(FlowchartResponseSerializer(payload).data)


class RulebookScriptView(APIView):
    """
    Game master 講稿 API（只讀，僅出已審核講稿；生成一律走 admin）

    GET /api/game/rulebooks/{rulebook_id}/script/?ruleset=basic
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Game master 教學講稿",
        description="讀取已審核（approved）的主持人教學講稿；未生成或未審核回 404",
        responses={200: ScriptResponseSerializer},
        parameters=[
            OpenApiParameter(
                name="rulebook_id", location=OpenApiParameter.PATH,
                description="規則書 UUID", required=True, type=str,
            ),
            OpenApiParameter(
                name="ruleset", location=OpenApiParameter.QUERY,
                description="變體名稱（預設 'basic'）",
                required=False, type=str,
            ),
        ],
    )
    def get(self, request, rulebook_id):
        get_object_or_404(Rulebook, pk=rulebook_id)
        ruleset = request.query_params.get("ruleset", "basic")

        obj = RulebookScript.objects.filter(
            rulebook_id=rulebook_id,
            ruleset=ruleset,
            is_published=True,
        ).first()
        if obj is None:
            return Response(
                {"error": "script_not_available"},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = {
            "title": obj.effective_title,
            "script_text": obj.effective_text,
            "language": obj.language.language,
            "is_adjusted": bool(obj.adjusted_text),
            "generated_at": obj.generated_at,
            "prompt_version": obj.prompt_version,
        }
        return Response(ScriptResponseSerializer(payload).data)


class RulebookFlowchartAdjustView(APIView):
    """
    PATCH /api/game/rulebooks/{rulebook_id}/flowchart/adjust/?ruleset=basic
    Body: {"detail": "concise"|"detailed", "adjusted_json": {...} | null}
    需要 game.change_rulebookflowchart 權限。Saves manual React Flow adjustments
    (with positions) to adjusted_json.
    Pass adjusted_json=null to clear and revert to the auto-generated version.
    目標圖以 (rulebook, ruleset) 定位;body 的 detail 僅保留向後相容驗證。
    存的是草稿：公開頁讀 FlowchartPublication，要等 reviewer 核准才會更新。
    """
    permission_classes = [CanEditFlowchart]

    def patch(self, request, rulebook_id):
        get_object_or_404(Rulebook, pk=rulebook_id)

        detail = request.data.get("detail")
        if detail not in ("concise", "detailed"):
            return Response(
                {"error": "detail must be 'concise' or 'detailed'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        adjusted = request.data.get("adjusted_json", "__missing__")
        if adjusted == "__missing__":
            return Response(
                {"error": "adjusted_json is required (pass null to revert)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ruleset = (
            request.data.get("ruleset")
            or request.query_params.get("ruleset")
            or "basic"
        )
        obj = RulebookFlowchart.objects.filter(
            rulebook_id=rulebook_id, ruleset=ruleset
        ).first()
        if not obj:
            return Response(
                {"error": "flowchart not found — generate it first"},
                status=status.HTTP_404_NOT_FOUND,
            )

        obj.adjusted_json = adjusted  # None clears it
        from game.flowchart_review import EDIT_FIELDS, mark_edited
        mark_edited(obj, request.user)
        obj.save(update_fields=["adjusted_json", "updated_at", *EDIT_FIELDS])

        effective_rf = obj.adjusted_json if obj.adjusted_json else obj.react_flow_json
        return Response({
            "detail": detail,
            "is_adjusted": bool(obj.adjusted_json),
            "react_flow": effective_rf,
            "updated_at": obj.updated_at,
        })


def _render_react_flow_html(title: str, obj) -> str:
    """Standalone read-only React Flow viewer page (uses the admin JS bundle)."""
    import json as _json
    import html as _html

    safe_title = _html.escape(title)
    effective_rf = obj.adjusted_json if obj.adjusted_json else obj.react_flow_json

    if not effective_rf:
        return (
            "<!doctype html><html><body style='font-family:sans-serif;padding:2rem'>"
            f"<h2>{safe_title}</h2>"
            "<p style='color:#888'>No React Flow data. Generate a flowchart first via the Rulebook admin action.</p>"
            "</body></html>"
        )

    info_bits = [
        f"detail={obj.detail}",
        f"ruleset={_html.escape(obj.ruleset or '')}",
        f"model={_html.escape(obj.llm_model or '')}",
        f"nodes={len(effective_rf.get('nodes') or [])}",
        f"edges={len(effective_rf.get('edges') or [])}",
        "adjusted" if obj.adjusted_json else "auto-generated",
    ]
    info_line = " · ".join(info_bits)

    config = {
        "reactFlowData": effective_rf,
        "adjustedJson": None,   # read-only: always use reactFlowData
        "adjustUrl": "",
        "csrfToken": "",
        "detail": obj.detail,
        "rulebookTitle": title,
        "isAdjusted": bool(obj.adjusted_json),
        "readOnly": True,
    }
    config_json = _json.dumps(config).replace("</", "<\\/")

    from django.contrib.staticfiles.storage import staticfiles_storage
    from game.templatetags.static_v import versioned_static
    js_url = versioned_static("game/admin/flowchart_editor/index.js")
    css_url = versioned_static("game/admin/flowchart_editor/index.css")
    theme_url = versioned_static("css/theme.css")

    return f"""<!doctype html>
<html lang="en" data-theme="default">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <link rel="stylesheet" href="{theme_url}">
  <link rel="stylesheet" href="{css_url}">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 0; height: 100vh; display: flex; flex-direction: column;
           font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .page-header {{ padding: 8px 16px; background: #f5f5f5; border-bottom: 1px solid #ddd;
                    flex-shrink: 0; display: flex; align-items: baseline; gap: 12px; }}
    .page-header h1 {{ margin: 0; font-size: 15px; color: #333; }}
    .page-header .meta {{ font-size: 11px; color: #888; }}
    #flowchart-editor-root {{ flex: 1; min-height: 0; }}
  </style>
</head>
<body>
  <div class="page-header">
    <h1>{safe_title}</h1>
    <span class="meta">{info_line}</span>
  </div>
  <div id="flowchart-editor-root"></div>
  <script>window.FLOWCHART_EDITOR_CONFIG = {config_json};</script>
  <script type="module" src="{js_url}"></script>
</body>
</html>
"""

