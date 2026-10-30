# game/sync_views.py
"""
VPS receiver-side API endpoints for game data sync.
These endpoints accept data from the local dev environment
and upsert into the VPS database / Qdrant / media storage.
"""
import json
import logging
import os
import tarfile
import tempfile

import requests as http_requests
from django.apps import apps
from django.conf import settings
from django.core import serializers as django_serializers
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def describe_exception(exc, limit=400, max_depth=4):
    """
    把例外描述成「類別: 訊息」並沿著 cause 鏈往下挖，回傳給 sender 端顯示。

    直接用 str(e) 會踩到一個坑：Django 的 JSON deserializer 在
    django/core/serializers/json.py 是 `raise DeserializationError() from exc`
    ——建構時沒帶任何參數，所以 str() 就是空字串，真正的原因（例如
    FieldDoesNotExist：VPS 少跑 migration、欄位對不上）全藏在 __cause__ 裡。
    只記 str(e) 的話 sender 端只會看到 "game.rulebookflowchart: " 一片空白。
    """
    parts = []
    seen = set()
    current = exc

    while current is not None and id(current) not in seen and len(parts) < max_depth:
        seen.add(id(current))
        text = str(current).strip()
        name = type(current).__name__
        parts.append(f"{name}: {text}" if text else name)
        current = current.__cause__ or current.__context__

    return " <- ".join(parts)[:limit]


# 內容重新產生時 PK 會換新，但 natural key 不變：VPS 上的舊 row 還在，而收資料時的
# pk-based exists 檢查看不到它，直接 INSERT 就撞 unique constraint。實際發生過的是
# uq_flowchart_rulebook_ruleset（重新生成流程圖），uq_script_rulebook_ruleset_language
# 是同一個坑。
#
# 不能直接把舊 row 刪掉了事：底下可能掛著只存在 VPS 的資料（會員送出的
# FlowchartSuggestion 是 on_delete=CASCADE，先刪就一起沒了）。順序是
# 讓出唯一鍵 → 存新 row → 依附資料轉掛 → 刪掉舊 row，整段都在同一個 transaction 內。
SUPERSEDE_RULES = {
    # model 名稱: (natural key 欄位, 要轉掛到新 row 的依附關係)
    "RulebookFlowchart": (
        ("rulebook_id", "ruleset"),
        (("game.FlowchartSuggestion", "flowchart_id"),
         ("game.RulebookScript", "source_flowchart_id"),
         # 審核紀錄是 CASCADE，不轉掛的話舊圖一刪整段審核歷史就跟著沒了
         ("game.FlowchartReview", "flowchart_id")),
    ),
    "RulebookScript": (
        ("rulebook_id", "ruleset", "language_id"),
        (),  # 沒有任何 FK 指向 RulebookScript
    ),
}


def free_natural_key(Model, obj):
    """natural key 撞到、但 PK 不同的舊 row：先讓出唯一鍵，回傳它們的 pk。"""
    rule = SUPERSEDE_RULES.get(Model.__name__)
    if not rule:
        return []

    key_fields, _ = rule
    lookup = {field: getattr(obj, field) for field in key_fields}
    superseded = list(
        Model.objects.filter(**lookup).exclude(pk=obj.pk).values_list("pk", flat=True)
    )
    # ruleset 是這些 model 共同的 natural key 欄位，改它就足以讓路
    for i, stale_pk in enumerate(superseded):
        Model.objects.filter(pk=stale_pk).update(
            ruleset=f"__superseded_{i}_{obj.pk}"[:100]
        )
    return superseded


# 同樣是「PK 換新、natural key 不變」的坑，但這些 model 沒有任何 FK 指向它們，
# 所以舊 row 直接刪掉就好，不需要 SUPERSEDE_RULES 那套讓位→轉掛→刪除的流程。
#   RulebookNode:            重新切塊會換新 UUID，撞 uq_rulebooknode_path_ruleset
#   FlowchartTextTranslation: PK 是各自獨立的 AutoField 序號，而 gc_flowchart_translations
#       ＋重譯會把列刪掉再新建，本機序號跟 VPS 早就漂開了；接收端的 pk-based
#       exists 檢查看不到 VPS 上同 text_hash 的舊列，INSERT 就撞 text_hash unique。
REPLACE_RULES = {
    "RulebookNode": ("rulebook_id", "tag_path", "ruleset"),
    "FlowchartTextTranslation": ("text_hash",),
}


# PK 各庫自己編、但名稱才是身分的 model：VPS 上若已有同名的列，就沿用它的 PK 覆寫，
# 不能刪（auth.Group 的成員關係掛在 PK 上，刪了 VPS 的使用者就失去群組）。
ALIGN_PK_BY_FIELD = {
    "Group": "name",
}


def align_pk_by_natural_key(Model, obj):
    field = ALIGN_PK_BY_FIELD.get(Model.__name__)
    if not field:
        return
    existing_pk = (
        Model.objects.filter(**{field: getattr(obj, field)})
        .values_list("pk", flat=True).first()
    )
    if existing_pk is not None and existing_pk != obj.pk:
        obj.pk = existing_pk


def drop_natural_key_conflicts(Model, obj):
    """
    刪掉 natural key 相同但 PK 不同的舊 row（這些 model 沒有依附資料要保）。

    不分 INSERT / UPDATE 都要跑：PK 會漂移，所以「pk 存在」也可能撞別人的
    natural key（VPS pk=2210 存著 hash Y、pk=120 存著 hash X，而本機 pk=2210
    現在是 hash X）。依定義這些舊 row 跟新 row 無法共存於 unique constraint 下，
    刪掉不會少掉任何能留的資料。
    """
    key_fields = REPLACE_RULES.get(Model.__name__)
    if not key_fields:
        return

    lookup = {field: getattr(obj, field) for field in key_fields}
    deleted, _ = Model.objects.filter(**lookup).exclude(pk=obj.pk).delete()
    if deleted:
        logger.info(
            "%s %s replaces %d stale row(s) matching %s",
            Model.__name__, obj.pk, deleted, lookup,
        )


def drop_superseded(Model, new_pk, superseded):
    """把依附資料轉掛到新 row，再刪掉被取代的舊 row。"""
    moved = 0
    for label, field in SUPERSEDE_RULES[Model.__name__][1]:
        Dependant = apps.get_model(label)
        moved += Dependant.objects.filter(
            **{f"{field}__in": superseded}
        ).update(**{field: new_pk})

    Model.objects.filter(pk__in=superseded).delete()
    logger.info(
        "%s %s supersedes %s (moved %d dependant row(s))",
        Model.__name__, new_pk, ", ".join(str(p) for p in superseded), moved,
    )


def apply_sync_layers(layers, sync_type):
    """
    把一包 layers（Django 序列化格式）upsert 進目前這個資料庫。

    VPS 接收本機推送（sync_game_data）與本機拉回 VPS 的流程圖（
    其他呼叫端）共用這一段，所以 PK 漂移、natural key 衝突的處理
    只有一份。回傳 (created, updated, deleted, errors)。
    """
    total_created = 0
    total_updated = 0
    total_deleted = 0
    errors = []

    for layer_group in layers:
        for entry in layer_group:
            model_label = entry["model"]
            data = entry["data"]

            try:
                json_str = json.dumps(data)

                with transaction.atomic():
                    saved_pks = set()

                    for deserialized_obj in django_serializers.deserialize("json", json_str):
                        Model = deserialized_obj.object.__class__
                        align_pk_by_natural_key(Model, deserialized_obj.object)
                        pk = deserialized_obj.object.pk
                        exists = Model.objects.filter(pk=pk).exists()

                        # PK 換新但 natural key 不變的 model（RulebookNode /
                        # FlowchartTextTranslation）：對方資料庫裡同 natural key 的舊 row
                        # 還佔著 unique constraint，而上面的 pk-based exists 檢查
                        # 看不到它。先清掉，否則寫入必撞 IntegrityError。
                        drop_natural_key_conflicts(Model, deserialized_obj.object)

                        # RulebookFlowchart / RulebookScript：重新產生會換新 PK，
                        # 舊 row 的 natural key 還佔著位子（見 SUPERSEDE_RULES）
                        superseded = [] if exists else free_natural_key(
                            Model, deserialized_obj.object
                        )

                        deserialized_obj.save()

                        if deserialized_obj.m2m_data:
                            for accessor_name, object_list in deserialized_obj.m2m_data.items():
                                getattr(deserialized_obj.object, accessor_name).set(object_list)

                        if superseded:
                            drop_superseded(Model, pk, superseded)

                        saved_pks.add(pk)

                        if exists:
                            total_updated += 1
                        else:
                            total_created += 1

                    # Full sync: delete records not in the payload
                    if sync_type == "full" and saved_pks and data:
                        deleted_count, _ = (
                            Model.objects.exclude(pk__in=saved_pks).delete()
                        )
                        total_deleted += deleted_count

            except Exception as e:
                error_msg = f"{model_label}: {describe_exception(e)}"
                logger.exception(f"Sync error for {model_label}")
                errors.append(error_msg)

    return total_created, total_updated, total_deleted, errors


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_game_data(request):
    """
    Receive and upsert DB records sent from local.
    Payload: {
        "sync_type": "delta" | "full",
        "layers": [
            [  # layer group
                {
                    "model": "game.entity",
                    "count": 5,
                    "data": [ ... django serialized objects ... ]
                },
            ],
        ]
    }
    """
    sync_type = request.data.get("sync_type", "delta")
    layers = request.data.get("layers", [])

    total_created, total_updated, total_deleted, errors = apply_sync_layers(layers, sync_type)

    result = {
        "result": "ok" if not errors else "partial",
        "created": total_created,
        "updated": total_updated,
        "deleted": total_deleted,
        "message": f"Created: {total_created}, Updated: {total_updated}, Deleted: {total_deleted}",
    }

    if errors:
        result["errors"] = errors[:10]

    return Response(result, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def sync_media(request):
    """
    Receive a tar.gz archive of media files and extract to MEDIA_ROOT.
    """
    archive_file = request.FILES.get("archive")
    if not archive_file:
        return Response(
            {"error": "No archive file provided"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    media_root = settings.MEDIA_ROOT
    extracted = 0

    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            for chunk in archive_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        with tarfile.open(tmp_path, "r:gz") as tar:
            for member in tar.getmembers():
                member_path = os.path.normpath(member.name)
                if member_path.startswith("..") or os.path.isabs(member_path):
                    logger.warning(f"Skipping unsafe path: {member.name}")
                    continue

                target_path = os.path.join(media_root, member_path)
                target_dir = os.path.dirname(target_path)
                os.makedirs(target_dir, exist_ok=True)

                if member.isfile():
                    with tar.extractfile(member) as src:
                        with open(target_path, "wb") as dst:
                            dst.write(src.read())
                    extracted += 1

        os.unlink(tmp_path)

        return Response({
            "result": "ok",
            "extracted": extracted,
            "message": f"Extracted {extracted} media files",
        })

    except Exception as e:
        logger.exception("Media sync failed")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def sync_qdrant(request, collection_name):
    """
    Receive Qdrant points and upsert to local Qdrant (point-level delta sync).

    Actions:
      - "upsert": Batch upsert points (zero downtime)
      - "cleanup": Delete points NOT in the valid_point_ids list (full sync only)
    """
    ALLOWED_COLLECTIONS = {"rulebook_nodes", "rulebook_qas"}

    if collection_name not in ALLOWED_COLLECTIONS:
        return Response(
            {"error": f"Collection '{collection_name}' not allowed"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    action = request.data.get("action", "upsert")
    qdrant_base = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"

    try:
        # Ensure collection exists
        _ensure_collection_exists(qdrant_base, collection_name)

        if action == "upsert":
            return _handle_qdrant_upsert(request, qdrant_base, collection_name)
        elif action == "cleanup":
            return _handle_qdrant_cleanup(request, qdrant_base, collection_name)
        else:
            return Response(
                {"error": f"Unknown action: {action}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        logger.exception(f"Qdrant sync failed for {collection_name}")
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


PAYLOAD_INDEXES = [
    ("rulebook_id", "keyword"),
    ("edition_id", "keyword"),
    ("game_id", "keyword"),
    ("language_code", "keyword"),
    ("category", "keyword"),
    ("has_figures", "bool"),
]


def _ensure_payload_indexes(qdrant_base, collection_name):
    """Mirror the payload indexes built by the local indexer."""
    for field_name, field_schema in PAYLOAD_INDEXES:
        resp = http_requests.put(
            f"{qdrant_base}/collections/{collection_name}/index",
            json={"field_name": field_name, "field_schema": field_schema},
            timeout=(5, 30),
        )
        # 200 = created, 409 = already exists; treat both as success
        if resp.status_code not in (200, 409):
            logger.warning(
                f"Failed to create payload index {field_name} on {collection_name}: "
                f"{resp.status_code} {resp.text[:200]}"
            )


def _ensure_collection_exists(qdrant_base, collection_name):
    """Create collection if it doesn't exist."""
    check_resp = http_requests.get(
        f"{qdrant_base}/collections/{collection_name}",
        timeout=(5, 10),
    )
    if check_resp.status_code == 404:
        # Create collection with embedding config from settings
        vector_size = getattr(settings, "EMBEDDING_DIMENSION", 768)
        create_resp = http_requests.put(
            f"{qdrant_base}/collections/{collection_name}",
            json={
                "vectors": {
                    "size": vector_size,
                    "distance": "Cosine",
                },
            },
            timeout=(10, 30),
        )
        if create_resp.status_code not in (200, 409):
            raise RuntimeError(
                f"Failed to create collection: {create_resp.status_code} {create_resp.text}"
            )
        logger.info(f"Created Qdrant collection: {collection_name}")
        _ensure_payload_indexes(qdrant_base, collection_name)
    else:
        # Collection already exists — make sure indexes are present too
        # (idempotent; existing indexes return 409)
        _ensure_payload_indexes(qdrant_base, collection_name)


def _handle_qdrant_upsert(request, qdrant_base, collection_name):
    """Upsert points to Qdrant."""
    points = request.data.get("points", [])
    if not points:
        return Response({"result": "ok", "upserted": 0, "message": "No points"})

    # Upsert via Qdrant REST API
    resp = http_requests.put(
        f"{qdrant_base}/collections/{collection_name}/points",
        json={"points": points},
        timeout=(10, 300),
    )

    if resp.status_code != 200:
        return Response(
            {"error": f"Qdrant upsert failed: {resp.status_code}", "detail": resp.text[:500]},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        "result": "ok",
        "upserted": len(points),
        "message": f"Upserted {len(points)} points to '{collection_name}'",
    })


def _handle_qdrant_cleanup(request, qdrant_base, collection_name):
    """Delete points not in the valid set (used during full sync)."""
    valid_ids = set(request.data.get("valid_point_ids", []))
    if not valid_ids:
        return Response({"result": "ok", "deleted": 0, "message": "No valid IDs provided"})

    # Scroll through all points in collection to find stale ones
    stale_ids = []
    offset = None

    while True:
        scroll_body = {"limit": 100, "with_payload": False, "with_vector": False}
        if offset is not None:
            scroll_body["offset"] = offset

        scroll_resp = http_requests.post(
            f"{qdrant_base}/collections/{collection_name}/points/scroll",
            json=scroll_body,
            timeout=(10, 60),
        )
        if scroll_resp.status_code != 200:
            break

        result = scroll_resp.json().get("result", {})
        points = result.get("points", [])
        next_offset = result.get("next_page_offset")

        for point in points:
            pid = str(point["id"])
            if pid not in valid_ids:
                stale_ids.append(pid)

        if next_offset is None or not points:
            break
        offset = next_offset

    # Delete stale points
    deleted = 0
    if stale_ids:
        del_resp = http_requests.post(
            f"{qdrant_base}/collections/{collection_name}/points/delete",
            json={"points": stale_ids},
            timeout=(10, 120),
        )
        if del_resp.status_code == 200:
            deleted = len(stale_ids)

    return Response({
        "result": "ok",
        "deleted": deleted,
        "message": f"Deleted {deleted} stale points from '{collection_name}'",
    })
