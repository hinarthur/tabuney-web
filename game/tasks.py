# game/tasks.py
import logging
from .models import RulebookStatus, Rulebook

logger = logging.getLogger(__name__)


def _count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def _detect_languages(chunks: list) -> list:
    """
    Detect languages from a list of text chunks (one per page or paragraph).
    Returns sorted list of language codes that appear with meaningful probability.
    Uses seed=0 for determinism and thread safety (langdetect default is non-deterministic).
    """
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0
        scores: dict = {}
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 40:
                continue
            try:
                for r in detect_langs(chunk[:3000]):
                    if r.prob > 0.12:
                        scores[r.lang] = scores.get(r.lang, 0) + r.prob
            except Exception:
                pass
        return sorted(scores)
    except Exception:
        return []


def process_rulebook_llamaparse_task(rulebook_id):
    """Background Task to extract rulebook text using LlamaParse v2."""
    rb = None
    try:
        rb = Rulebook.objects.get(id=rulebook_id)
        logger.warning(f"[LlamaParse] Task started for Rulebook: {rb.title} ({rb.id})")

        from .rag.rulebook_processing import (
            extract_rulebook_with_llamaparse,
            validate_rulebook_markdown,
        )

        # 一次讀完 PDF bytes，分別給 fitz 計頁數與 LlamaParse 使用
        # FieldFile.read() 會自動開檔；不要先呼叫 seek（檔尚未開）
        import io
        import fitz
        rb.file.open("rb")
        try:
            pdf_bytes = rb.file.read()
        finally:
            rb.file.close()

        expected_pages = None
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                expected_pages = doc.page_count
        except Exception as e:
            logger.warning(f"[LlamaParse] Could not pre-count pages for {rulebook_id}: {e}")

        buf = io.BytesIO(pdf_bytes)
        buf.name = rb.file.name
        text, needs_ocr = extract_rulebook_with_llamaparse(buf, language=rb.language.language)

        rb.extracted_text = text
        rb.needs_ocr = needs_ocr
        rb.ocr_done = True
        rb.status = RulebookStatus.PARSED
        rb.last_error = ""
        rb.pdf_token_count = _count_tokens(text)
        import re as _re
        rb.content_languages = _detect_languages(_re.split(r"\n{2,}|<PAGE:\d+>", text))

        rb.save(update_fields=[
            "extracted_text", "needs_ocr", "ocr_done",
            "status", "last_error", "pdf_token_count", "content_languages", "updated_at"
        ])

        warnings = validate_rulebook_markdown(text, expected_pages=expected_pages)
        if warnings:
            logger.warning(
                f"[LlamaParse] Rulebook {rb.title} ({rb.id}) passed extraction but failed "
                f"{len(warnings)} formatting rule(s):"
            )
            for w in warnings:
                logger.warning(f"  - {w}")
        else:
            logger.warning(f"[LlamaParse] Rulebook {rb.title} ({rb.id}) passed all formatting rules.")
        logger.warning(f"[LlamaParse] Task completed for Rulebook: {rb.title}")

    except Rulebook.DoesNotExist:
        logger.error(f"[LlamaParse] Task failed: Rulebook {rulebook_id} not found.")
    except Exception as e:
        logger.exception(f"[LlamaParse] Task failed for Rulebook {rulebook_id}: {str(e)}")
        if rb:
            try:
                rb.mark_extract_failed(e)
            except Exception as save_error:
                logger.error(f"Failed to mark Rulebook {rulebook_id} as failed: {save_error}")


def process_rulebook_whole_context_task(rulebook_id):
    """
    Background Task：LlamaParse 全文擷取。

    寫入策略：只寫 extracted_text，絕不寫 whole_context。

    - extracted_text：每次都覆寫，保存這次 LlamaParse 的原始產出。
      全站只有這裡會寫它、沒有任何流程讀它（chunking 讀的是 processed_text），
      所以拿來當「機器原稿」不會影響其他 pipeline。
    - whole_context：這條路徑一律不碰。它是人工調整區，rulesbot / flowchart /
      script 都吃這個欄位，要換成新原稿一律在 admin 編輯頁把 extracted_text
      複製貼上過去——刻意不做任何「空的就種入」之類的條件判斷，行為只有一種，
      不必去記這次到底會不會動到 whole_context。

    刻意不碰 status / pdf_token_count / content_languages —— 那些是舊 extract
    流程的欄位，這條路徑不該污染，才能在同一本規則書上做 A/B 對比。
    """
    rb = None
    try:
        rb = Rulebook.objects.get(id=rulebook_id)
        logger.warning(f"[WholeContext] Task started for Rulebook: {rb.title} ({rb.id})")

        from .rag.rulebook_processing import extract_rulebook_whole_context

        import io
        rb.file.open("rb")
        try:
            pdf_bytes = rb.file.read()
        finally:
            rb.file.close()

        buf = io.BytesIO(pdf_bytes)
        buf.name = rb.file.name
        text, _ = extract_rulebook_whole_context(buf, language=rb.language.language)

        rb.extracted_text = text
        rb.save(update_fields=["extracted_text", "updated_at"])

        logger.warning(
            f"[WholeContext] Task completed for Rulebook: {rb.title} "
            f"({len(text)} chars, ~{_count_tokens(text)} tokens); "
            f"extracted_text updated, whole_context untouched"
        )

    except Rulebook.DoesNotExist:
        logger.error(f"[WholeContext] Task failed: Rulebook {rulebook_id} not found.")
    except Exception as e:
        logger.exception(f"[WholeContext] Task failed for Rulebook {rulebook_id}: {str(e)}")
        if rb:
            try:
                # 只留錯誤訊息，不動 status —— mark_extract_failed() 會把 status 打成
                # failed，那是舊 extract 流程的狀態，不該被這條實驗路徑覆寫。
                rb.last_error = f"[WHOLE] {e}"[:1000]
                rb.save(update_fields=["last_error", "updated_at"])
            except Exception as save_error:
                logger.error(f"Failed to record error for Rulebook {rulebook_id}: {save_error}")


def process_rulebook_pymupdf_task(rulebook_id):
    """Background Task to extract rulebook text using PyMuPDF (with OCR fallback)."""
    rb = None
    try:
        rb = Rulebook.objects.get(id=rulebook_id)
        logger.warning(f"[PyMuPDF] Task started for Rulebook: {rb.title} ({rb.id})")

        from .rag.rulebook_processing import extract_text_from_pdf_with_ocr
        language = rb.language.language if rb.language else "en"
        text, needs_ocr = extract_text_from_pdf_with_ocr(rb.file, language=language)

        rb.extracted_text = text
        rb.needs_ocr = needs_ocr
        rb.ocr_done = True
        rb.status = RulebookStatus.PARSED
        rb.last_error = ""
        rb.pdf_token_count = _count_tokens(text)
        import re as _re
        rb.content_languages = _detect_languages(_re.split(r"\n{2,}|<PAGE:\d+>", text))

        rb.save(update_fields=[
            "extracted_text", "needs_ocr", "ocr_done",
            "status", "last_error", "pdf_token_count", "content_languages", "updated_at"
        ])
        logger.warning(f"[PyMuPDF] Task completed for Rulebook: {rb.title}")

    except Rulebook.DoesNotExist:
        logger.error(f"[PyMuPDF] Task failed: Rulebook {rulebook_id} not found.")
    except Exception as e:
        logger.exception(f"[PyMuPDF] Task failed for Rulebook {rulebook_id}: {str(e)}")
        if rb:
            try:
                rb.mark_extract_failed(e)
            except Exception as save_error:
                logger.error(f"Failed to mark Rulebook {rulebook_id} as failed: {save_error}")


def process_rag_ingest_task(rulebook_id):
    """Background Task to chunk and index rulebook."""
    try:
        rb = Rulebook.objects.get(id=rulebook_id)
    except Rulebook.DoesNotExist:
        logger.error(f"[RAG Ingest] Rulebook {rulebook_id} not found.")
        raise

    logger.info(f"[RAG Ingest] Task started for Rulebook: {rb.title} ({rb.id})")
    from .rag.ingest import ingest_rulebook_full
    msg = ingest_rulebook_full(rb)
    logger.info(f"[RAG Ingest] Task completed for Rulebook: {rb.title}. Result: {msg}")
    return msg


def generate_flowcharts_task(rulebook_id, ruleset="basic", regenerate=True, details=None, model=None):
    """
    Background Task: generate flowchart(s) for one rulebook.

    details: list of detail levels to generate, e.g. ["concise"] or ["detailed"];
             None defaults to ["detailed"].
    model:   None 用 Gemini 預設模型；也可指定 "gemini-*" / "claude-*" / "gpt-*"
             來比較不同模型的生成效果（見 FlowchartService._call_provider）。
    """
    from .rag.flowchart import get_flowchart_service
    from .rag.flowchart.service import FlowchartGenerationError

    if details is None:
        details = ["detailed"]

    try:
        rb = Rulebook.objects.get(id=rulebook_id)
    except Rulebook.DoesNotExist:
        logger.error(f"[Flowchart] Rulebook {rulebook_id} not found.")
        raise

    edition_id = str(rb.edition_id) if rb.edition_id else None
    svc = get_flowchart_service()
    results = {}
    for detail in details:
        logger.info(
            f"[Flowchart] Generating {detail} for Rulebook: {rb.title} ({rb.id}) "
            f"model={model or 'default'}"
        )
        try:
            obj, cached = svc.get_or_generate(
                rulebook_id=str(rb.id),
                edition_id=edition_id,
                ruleset=ruleset,
                detail=detail,
                regenerate=regenerate,
                model=model,
            )
            results[detail] = {
                "ok": True,
                "cached": cached,
                "nodes": len((obj.intermediate_json or {}).get("nodes", [])),
                "model": obj.llm_model,
            }
        except FlowchartGenerationError as e:
            results[detail] = {"ok": False, "error": str(e)}
            logger.warning(f"[Flowchart] {detail} generation_error for {rb.title}: {e}")
        except Exception as e:
            results[detail] = {"ok": False, "error": str(e)}
            logger.exception(f"[Flowchart] {detail} failed for {rb.title}: {e}")

    logger.info(f"[Flowchart] Done for Rulebook: {rb.title}. Results: {results}")
    return results


def generate_script_task(script_id):
    """
    Background Task: generate the game-master teaching script for one
    RulebookScript row (persona/atmosphere already filled in admin).
    """
    from .rag.script import get_script_service

    logger.info(f"[Script] Task started for RulebookScript {script_id}")
    obj = get_script_service().generate(script_id)  # 失敗時 service 已標 FAILED 再 raise
    chars = len(obj.script_text or "")
    logger.info(f"[Script] Done for RulebookScript {script_id}: {chars} chars")
    return {"ok": True, "chars": chars}


def check_rulebook_source_urls_task():
    """Django-Q 排程用：檢查所有 Rulebook.source_url 是否仍可開啟。"""
    from django.core.management import call_command
    call_command("check_rulebook_source_urls")
