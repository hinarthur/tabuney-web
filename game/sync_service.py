# game/sync_service.py
"""
Sender-side sync service: collects changed data from local DB,
serializes it, and sends to VPS via REST API.

Usage (from admin action):
    from game.sync_service import GameSyncService
    service = GameSyncService()
    log = service.run(sync_type="delta")
"""
import io
import json
import os
import tarfile
import logging
from datetime import datetime

import requests as http_requests
from django.apps import apps
from django.conf import settings
from django.core import serializers as django_serializers
from django.db.models import Q
from django.utils import timezone

from game.sync_models import GameSyncLog

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Sync spec: models in FK-dependency order
# ─────────────────────────────────────────────

SYNC_LAYERS = [
    # Layer 0: no FK dependencies
    [
        ("translation", "Tribe"),
        ("translation", "Region"),
        ("commerce", "Currency"),
        ("ad", "Artwork"),
    ],
    # Layer 1
    [
        ("game", "Entity"),
        ("ad", "Affiliate"),
        ("ad", "CallToAction"),
    ],
    # Layer 2
    [
        ("game", "Game"),
    ],
    # Layer 3
    [
        ("game", "GameTitle"),
        ("game", "Edition"),
    ],
    # Layer 4
    [
        ("game", "EditionRole"),
        ("game", "EditionSlugAlias"),
        ("game", "Rulebook"),
    ],
    # Layer 5: Flowcharts（只送 reviewer 核准過的圖；下架的也要送，
    # 它的 publication.is_live=False 才傳得過去）
    [
        ("game", "RulebookFlowchart", {"publication__isnull": False}),
    ],
    # Layer 6
    [
        ("game", "RulebookNode"),
        # 只同步已發布的講稿，草稿/未審核內容不外流到 VPS（比照流程圖只同步核可過的）。
        ("game", "RulebookScript", {"is_published": True}),
        # 流程圖公開版快照（VPS 公開頁讀這個）。FK 指向 Layer 5 的 RulebookFlowchart。
        # FlowchartReview（審核紀錄）刻意不同步：只在本機，且 User FK 對不上 VPS。
        ("game", "FlowchartPublication"),
    ],
]

# 不送到 VPS 的欄位：指向本機 User 的 FK，VPS 上 User id 對不上，送過去會撞 FK
# 限制。接收端反序列化時缺欄位就用預設值（None）。
SYNC_EXCLUDED_FIELDS = {
    "game.rulebookflowchart": {"content_edited_by"},
}


def _strip_local_fields(model_label, records):
    excluded = SYNC_EXCLUDED_FIELDS.get(model_label.lower())
    if excluded:
        for rec in records:
            for name in excluded:
                rec.get("fields", {}).pop(name, None)
    return records


# FlowchartTextTranslation（流程圖文字的多語譯文）刻意不列在 SYNC_LAYERS：
# 它的 delta 條件跟其他 model 不一樣（見 _collect_flowchart_texts），要另外算。
# 而同一個 model 在一次 full sync 出現兩筆 entry 會互相刪掉對方剛存進去的列
# （接收端每筆 entry 各自跑 exclude(pk__in=saved_pks).delete()，見
# sync_views.sync_game_data），所以這張表只能有單一來源。

# Media directories to include (relative to MEDIA_ROOT)
MEDIA_INCLUDE_PREFIXES = [
    "edition_thumbnails/",
    "ad/",
    "sitelogo/",
]

# Explicitly exclude
MEDIA_EXCLUDE_PREFIXES = [
    "rulebooks/",
]

# 一次 media upload 的原始檔案量上限（壓縮前）。Full sync 全部檔案約 130 MB，
# 塞進單一 POST 會撞上傳逾時（見 _send_media_batch）與 nginx body 上限。
MEDIA_BATCH_BYTES = 20 * 1024 * 1024

# 單一 media batch 上傳允許的秒數（同時涵蓋 body 寫入，見 _send_media_batch）。
MEDIA_UPLOAD_TIMEOUT = 300

# Qdrant collections to sync (delta upsert, NOT snapshot)
QDRANT_COLLECTIONS = {
    "rulebook_nodes": ("game", "RulebookNode"),
    "rulebook_qas": ("game", "RulebookQA"),
}

# Batch size for Qdrant point operations
QDRANT_BATCH_SIZE = 100


class GameSyncService:
    """Handles syncing game data from local → VPS."""

    def __init__(self):
        self.vps_base = getattr(settings, "VPS_SYNC_BASE_URL", "https://tabuney.com")
        self.username = settings.VPS_API_USERNAME
        self.password = settings.VPS_API_PASSWORD
        self.qdrant_host = settings.QDRANT_HOST
        self.qdrant_port = settings.QDRANT_PORT

    # ─── Main entry point ───────────────────────────

    def run(self, sync_type="delta"):
        """
        Execute a full sync operation.
        Returns the GameSyncLog instance.
        """
        since = None
        if sync_type == "delta":
            since = self._get_last_sync_time()

        sync_log = GameSyncLog.objects.create(
            sync_type=sync_type,
            since=since,
        )

        errors = []
        total_records = 0
        total_media = 0
        details = {}

        try:
            # 1. Get JWT token
            token = self._get_auth_token()

            # 2. Collect & send DB records (Layer by Layer to avoid 413 Entity Too Large)
            layers_payload, record_count, model_stats = self._collect_db_records(since)
            total_records = record_count
            details["models"] = model_stats

            if record_count > 0:
                db_all_ok = True
                db_msgs = []
                for layer_data in layers_payload:
                    db_ok, db_msg = self._send_db_records(token, {"layers": [layer_data]}, sync_type)
                    if not db_ok:
                        db_all_ok = False
                        errors.append(f"DB sync: {db_msg}")
                    db_msgs.append(db_msg)
                details["db_sync"] = db_msgs[0] if len(db_msgs) == 1 else db_msgs
            else:
                details["db_sync"] = "No changed records"

            # 3. Collect & send media files
            media_paths = self._collect_media_files(since)
            details["media_files"] = len(media_paths)

            if media_paths:
                media_ok, total_media, media_msg = self._send_media_files(token, media_paths)
                if not media_ok:
                    errors.append(f"Media sync: {media_msg}")
                details["media_sync"] = media_msg
            else:
                details["media_sync"] = "No media files to sync"

            # 4. Qdrant delta sync (point-level upsert, zero downtime)
            qdrant_results = {}
            qdrant_all_ok = True
            for collection, (app_label, model_name) in QDRANT_COLLECTIONS.items():
                q_ok, q_msg = self._sync_qdrant_delta(
                    token, collection, app_label, model_name, since, sync_type
                )
                qdrant_results[collection] = q_msg
                if not q_ok:
                    qdrant_all_ok = False
                    errors.append(f"Qdrant [{collection}]: {q_msg}")
            details["qdrant"] = qdrant_results

            # 5. Record result
            if errors:
                sync_log.mark_partial(
                    error_msg="\n".join(errors),
                    records_sent=total_records,
                    media_sent=total_media,
                    qdrant_synced=qdrant_all_ok,
                    details=details,
                )
            else:
                sync_log.mark_success(
                    records_sent=total_records,
                    media_sent=total_media,
                    qdrant_synced=True,
                    details=details,
                )

        except Exception as e:
            logger.exception("Sync failed")
            sync_log.mark_failed(str(e))

        return sync_log

    def sync_affiliates(self, affiliate_queryset):
        """
        Manually sync specific affiliates and their dependencies.
        """
        sync_log = GameSyncLog.objects.create(
            sync_type="manual",
            since=None,
        )

        errors = []
        total_records = 0
        total_media = 0
        details = {}

        try:
            token = self._get_auth_token()

            # 1. Collect records
            # Artworks (Layer 0)
            artwork_ids = affiliate_queryset.filter(artwork__isnull=False).values_list('artwork_id', flat=True).distinct()
            from ad.models import Artwork
            artworks = Artwork.objects.filter(id__in=artwork_ids)
            
            # CallToActions (Layer 1)
            cta_names = affiliate_queryset.filter(cta_name__isnull=False).exclude(cta_name='').values_list('cta_name', flat=True).distinct()
            from ad.models import CallToAction
            ctas = CallToAction.objects.filter(name__in=cta_names)

            # Build Layers
            # Layer 0: Artworks
            layer0_data = []
            if artworks.exists():
                json_str = django_serializers.serialize("json", artworks)
                layer0_data.append({
                    "model": "ad.artwork",
                    "count": artworks.count(),
                    "data": json.loads(json_str),
                })
                total_records += artworks.count()

            # Layer 1: Affiliates & CTAs
            layer1_data = []
            # Affiliates
            json_str = django_serializers.serialize("json", affiliate_queryset)
            layer1_data.append({
                "model": "ad.affiliate",
                "count": affiliate_queryset.count(),
                "data": json.loads(json_str),
            })
            total_records += affiliate_queryset.count()
            # CTAs
            if ctas.exists():
                json_str = django_serializers.serialize("json", ctas)
                layer1_data.append({
                    "model": "ad.calltoaction",
                    "count": ctas.count(),
                    "data": json.loads(json_str),
                })
                total_records += ctas.count()

            # Send DB Layers
            for idx, layer_entries in enumerate([layer0_data, layer1_data]):
                if layer_entries:
                    ok, msg = self._send_db_records(token, {"layers": [layer_entries]}, "manual")
                    if not ok:
                        errors.append(f"DB Layer {idx} failed: {msg}")

            # 2. Collect Media Files
            media_paths = []
            for art in artworks:
                if art.image:
                    media_paths.append(art.image.path)
            
            if media_paths:
                ok, total_media, msg = self._send_media_files(token, media_paths)
                if not ok:
                    errors.append(f"Media sync failed: {msg}")

            # 3. Record Result
            if errors:
                sync_log.mark_partial(
                    error_msg="\n".join(errors),
                    records_sent=total_records,
                    media_sent=total_media,
                    qdrant_synced=False,
                    details=details,
                )
            else:
                sync_log.mark_success(
                    records_sent=total_records,
                    media_sent=total_media,
                    qdrant_synced=False,
                    details=details,
                )

        except Exception as e:
            logger.exception("Manual affiliate sync failed")
            sync_log.mark_failed(str(e))

        return sync_log

    def sync_games(self, game_queryset):
        """
        Force sync specific games and all their related dependencies.
        """
        sync_log = GameSyncLog.objects.create(
            sync_type="manual",
            since=None,
        )

        errors = []
        total_records = 0
        total_media = 0
        details = {}

        try:
            token = self._get_auth_token()
            game_ids = list(game_queryset.values_list('id', flat=True))
            if not game_ids:
                return sync_log

            # 1. Collect records layer by layer
            from game.models import (
                GameTitle, Edition,
                EditionRole, Rulebook, Entity
            )
            from ad.models import Affiliate, Artwork, CallToAction

            # Pre-collect IDs to avoid deep nested queries during serialization
            affiliate_ids = list(game_queryset.filter(affiliate__isnull=False).values_list('affiliate_id', flat=True).distinct())
            affiliates = Affiliate.objects.filter(id__in=affiliate_ids)
            artwork_ids = list(affiliates.filter(artwork__isnull=False).values_list('artwork_id', flat=True).distinct())
            cta_names = list(affiliates.filter(cta_name__isnull=False).exclude(cta_name='').values_list('cta_name', flat=True).distinct())

            edition_ids = list(Edition.objects.filter(game_id__in=game_ids).values_list('id', flat=True))
            edition_role_entities = list(EditionRole.objects.filter(edition_id__in=edition_ids).values_list('entity_id', flat=True).distinct())
            rulebook_ids = list(Rulebook.objects.filter(edition_id__in=edition_ids).values_list('id', flat=True))

            # Build Payload Structure
            layers_to_send = []

            # Layer 0: Artworks, Entities
            l0 = []
            artworks = Artwork.objects.filter(id__in=artwork_ids)
            if artworks.exists():
                l0.append({"model": "ad.artwork", "count": artworks.count(), "data": json.loads(django_serializers.serialize("json", artworks))})
            entities = Entity.objects.filter(id__in=edition_role_entities)
            if entities.exists():
                l0.append({"model": "game.entity", "count": entities.count(), "data": json.loads(django_serializers.serialize("json", entities))})
            if l0: layers_to_send.append(l0)

            # Layer 1: Affiliates, CTAs
            l1 = []
            if affiliates.exists():
                l1.append({"model": "ad.affiliate", "count": affiliates.count(), "data": json.loads(django_serializers.serialize("json", affiliates))})
            ctas = CallToAction.objects.filter(name__in=cta_names)
            if ctas.exists():
                l1.append({"model": "ad.calltoaction", "count": ctas.count(), "data": json.loads(django_serializers.serialize("json", ctas))})
            if l1: layers_to_send.append(l1)

            # Layer 2: Games
            l2 = [{"model": "game.game", "count": game_queryset.count(), "data": json.loads(django_serializers.serialize("json", game_queryset))}]
            layers_to_send.append(l2)

            # Layer 3: GameTitles, Editions
            l3 = []
            titles = GameTitle.objects.filter(game_id__in=game_ids)
            if titles.exists():
                l3.append({"model": "game.gametitle", "count": titles.count(), "data": json.loads(django_serializers.serialize("json", titles))})
            editions = Edition.objects.filter(game_id__in=game_ids)
            if editions.exists():
                l3.append({"model": "game.edition", "count": editions.count(), "data": json.loads(django_serializers.serialize("json", editions))})
            if l3: layers_to_send.append(l3)

            # Layer 4: EditionRoles, Rulebooks
            l4 = []
            roles = EditionRole.objects.filter(edition_id__in=edition_ids)
            if roles.exists():
                l4.append({"model": "game.editionrole", "count": roles.count(), "data": json.loads(django_serializers.serialize("json", roles))})
            rulebooks = Rulebook.objects.filter(edition_id__in=edition_ids)
            if rulebooks.exists():
                l4.append({"model": "game.rulebook", "count": rulebooks.count(), "data": json.loads(django_serializers.serialize("json", rulebooks))})
            if l4: layers_to_send.append(l4)

            # Layer 5: RulebookFlowcharts（只送 reviewer 核准過的，含已下架的）
            l5 = []
            from game.models import FlowchartPublication, RulebookFlowchart
            flowcharts = RulebookFlowchart.objects.filter(
                rulebook_id__in=rulebook_ids, publication__isnull=False,
            )
            if flowcharts.exists():
                l5.append(self._serialize_entry("game.rulebookflowchart", flowcharts))
                # 這批圖在 VPS 上在地化要用的譯文：不送過去圖只會顯示原文。
                # 這裡不看 updated_at，整批補齊（manual sync 不做刪除，重送無害）。
                text_entry = self._serialize_entry(
                    "game.flowcharttexttranslation",
                    self._flowchart_texts_for(flowcharts),
                )
                if text_entry:
                    l5.append(text_entry)
            if l5: layers_to_send.append(l5)

            # Layer 6: RulebookScripts (published only, 比照 flowchart 只同步核可內容)、
            # 流程圖公開版快照（FK 指向 Layer 5 的圖）
            l6 = []
            from game.models import RulebookScript
            scripts = RulebookScript.objects.filter(rulebook_id__in=rulebook_ids, is_published=True)
            if scripts.exists():
                l6.append({"model": "game.rulebookscript", "count": scripts.count(), "data": json.loads(django_serializers.serialize("json", scripts))})
            publications = FlowchartPublication.objects.filter(flowchart__rulebook_id__in=rulebook_ids)
            if publications.exists():
                l6.append(self._serialize_entry("game.flowchartpublication", publications))
            if l6: layers_to_send.append(l6)

            # Send DB records
            total_records = 0
            for idx, layer_data in enumerate(layers_to_send):
                layer_count = sum(m["count"] for m in layer_data)
                total_records += layer_count
                ok, msg = self._send_db_records(token, {"layers": [layer_data]}, "manual")
                if not ok:
                    errors.append(f"DB Layer {idx} failed: {msg}")

            # 2. Collect Media Files
            media_paths = []
            # Artwork images
            for art in artworks:
                if art.image: media_paths.append(art.image.path)
            # Edition thumbnails
            for ed in editions:
                if ed.thumbnail: media_paths.append(ed.thumbnail.path)
            
            if media_paths:
                ok, total_media, msg = self._send_media_files(token, media_paths)
                if not ok:
                    errors.append(f"Media sync failed: {msg}")

            # 3. Vector Sync (Rulebook chunks & QAs)
            qdrant_all_ok = True
            for collection, (app_label, model_name) in QDRANT_COLLECTIONS.items():
                if model_name == "RulebookNode":
                    # For a manual sync, we only care about nodes related to our games
                    q_ok, q_msg = self._sync_qdrant_delta(token, collection, app_label, model_name, since=None, sync_type="manual_game", game_ids=game_ids)
                elif model_name == "RulebookQA":
                    q_ok, q_msg = self._sync_qdrant_delta(token, collection, app_label, model_name, since=None, sync_type="manual_game", game_ids=game_ids)
                else:
                    continue
                if not q_ok:
                    qdrant_all_ok = False
                    errors.append(f"Qdrant [{collection}]: {q_msg}")

            # 4. Record result
            if errors:
                sync_log.mark_partial(error_msg="\n".join(errors), records_sent=total_records, media_sent=total_media, qdrant_synced=qdrant_all_ok)
            else:
                sync_log.mark_success(records_sent=total_records, media_sent=total_media, qdrant_synced=qdrant_all_ok)

        except Exception as e:
            logger.exception("Manual game sync failed")
            sync_log.mark_failed(str(e))

        return sync_log

    def sync_flowchart_texts(self):
        """
        把「所有已發布流程圖」引用到的譯文整批推上 VPS（不刪除任何東西）。

        存在的理由是 delta 補不了歷史：delta 只會補上「這次一起送出的圖」所
        引用的譯文（見 _collect_flowchart_texts），早就同步過、updated_at 沒再
        變動的舊圖不會被帶到，那些圖在 VPS 上就一直只有原文。這個 action 是
        一次性的 backfill——跑過一次之後，新圖與改過的譯文靠 delta 就夠了。

        用 sync_type="manual" 送出，接收端只 upsert 不刪除：這張表是以
        sha256 去重的全站共用快取，本機的孤兒清理有 gc_flowchart_translations
        負責，不該由同步順手在 VPS 上做刪除。
        """
        from game.models import RulebookFlowchart

        sync_log = GameSyncLog.objects.create(sync_type="manual", since=None)

        try:
            charts = RulebookFlowchart.objects.published()
            entry = self._serialize_entry(
                "game.flowcharttexttranslation",
                self._flowchart_texts_for(charts),
            )

            if entry is None:
                sync_log.mark_success(
                    records_sent=0, media_sent=0, qdrant_synced=False,
                    details={"models": {}, "db_sync": "No flowchart translations to send"},
                )
                return sync_log

            token = self._get_auth_token()
            ok, msg = self._send_db_records(token, {"layers": [[entry]]}, "manual")

            details = {
                "models": {"game.FlowchartTextTranslation": entry["count"]},
                "published_charts": charts.count(),
                "db_sync": msg,
            }

            if ok:
                sync_log.mark_success(
                    records_sent=entry["count"], media_sent=0,
                    qdrant_synced=False, details=details,
                )
            else:
                sync_log.mark_partial(
                    error_msg=f"DB sync: {msg}", records_sent=0, media_sent=0,
                    qdrant_synced=False, details=details,
                )

        except Exception as e:
            logger.exception("Flowchart text sync failed")
            sync_log.mark_failed(str(e))

        return sync_log

    def sync_tiers(self, tier_queryset):
        """
        Push member.Tier settings (code / name / limits) to VPS.

        Tier 沒有 FK、沒有媒體檔，所以只送單一 layer。
        用 sync_type="manual" 送出 → 接收端只做 upsert，不會刪除 VPS 上
        沒被選到的 tier。full sync 的刪除在這裡是真的有害：沒有會員掛著的
        tier（例如 'admin'）會被乾淨刪掉，PROTECT 攔不住，而 commerce/views.py
        的 Tier.objects.get(code=...) 是 try/except DoesNotExist: pass，
        會變成付款後靜默不升等。
        """
        sync_log = GameSyncLog.objects.create(
            sync_type="manual",
            since=None,
        )

        try:
            count = tier_queryset.count()
            if count == 0:
                sync_log.mark_success(
                    records_sent=0,
                    media_sent=0,
                    qdrant_synced=False,
                    details={"models": {}},
                )
                return sync_log

            token = self._get_auth_token()

            layer = [
                {
                    "model": "member.tier",
                    "count": count,
                    "data": json.loads(
                        django_serializers.serialize("json", tier_queryset)
                    ),
                }
            ]

            ok, msg = self._send_db_records(token, {"layers": [layer]}, "manual")
            details = {
                "models": {"member.Tier": count},
                "codes": list(tier_queryset.values_list("code", flat=True)),
                "db_sync": msg,
            }

            if ok:
                sync_log.mark_success(
                    records_sent=count,
                    media_sent=0,
                    qdrant_synced=False,
                    details=details,
                )
            else:
                sync_log.mark_partial(
                    error_msg=f"DB sync: {msg}",
                    records_sent=0,
                    media_sent=0,
                    qdrant_synced=False,
                    details=details,
                )

        except Exception as e:
            logger.exception("Manual tier sync failed")
            sync_log.mark_failed(str(e))

        return sync_log

    def sync_groups(self, group_queryset):
        """
        Push auth.Group（名稱＋權限）到 VPS。只送群組本身，不送 User 與其成員關係。

        權限用 natural key（codename, app_label, model）序列化：Permission 的 PK 是
        各資料庫 migrate 時自己編的，本機與 VPS 的序號不保證一致，送 PK 會把群組
        掛到錯的權限上。接收端對同名但 PK 不同的群組會沿用 VPS 上既有那筆（見
        sync_views.align_pk_by_natural_key），並把權限整組設成與本機相同。

        用 sync_type="manual" 送出，接收端只 upsert、不刪除 VPS 上其他群組。
        VPS 上缺少某個權限（例如 VPS 還沒跑對應的 migration）時該群組會整筆失敗。
        """
        sync_log = GameSyncLog.objects.create(sync_type="manual", since=None)

        try:
            count = group_queryset.count()
            if count == 0:
                sync_log.mark_success(
                    records_sent=0, media_sent=0, qdrant_synced=False,
                    details={"models": {}},
                )
                return sync_log

            token = self._get_auth_token()
            layer = [{
                "model": "auth.group",
                "count": count,
                "data": json.loads(django_serializers.serialize(
                    "json", group_queryset, use_natural_foreign_keys=True,
                )),
            }]

            ok, msg = self._send_db_records(token, {"layers": [layer]}, "manual")
            details = {
                "models": {"auth.Group": count},
                "names": list(group_queryset.values_list("name", flat=True)),
                "db_sync": msg,
            }
            if ok:
                sync_log.mark_success(
                    records_sent=count, media_sent=0, qdrant_synced=False, details=details,
                )
            else:
                sync_log.mark_partial(
                    error_msg=f"DB sync: {msg}", records_sent=0, media_sent=0,
                    qdrant_synced=False, details=details,
                )
        except Exception as e:
            logger.exception("Manual group sync failed")
            sync_log.mark_failed(str(e))

        return sync_log

    # ─── Auth ───────────────────────────────────────

    def _get_auth_token(self):
        """Get JWT access token from VPS."""
        resp = http_requests.post(
            f"{self.vps_base}/api/token/",
            json={"username": self.username, "password": self.password},
            timeout=(10, 30),
        )
        resp.raise_for_status()
        token = resp.json().get("access")
        if not token:
            raise RuntimeError("VPS auth succeeded but no access token returned")
        return token

    def _auth_headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    # ─── Last sync time ─────────────────────────────

    def _get_last_sync_time(self):
        """
        Delta 的基準點：最後一次「完整送完整批資料」的同步時間。

        只認 status="success"：partial 代表有東西沒送成功，若拿它當基準點，
        那些失敗的記錄下一輪就會因為 updated_at <= since 被濾掉、永遠補不回來。
        改成只認 success 後，partial 之後的下一次 delta 會把失敗的那批重送
        （upsert 本來就是冪等的）。

        只認 delta/full：manual 同步只推人工挑選的少數記錄（例如單一 Tier、
        指定 affiliate），不是全面的基準線，不能拿來推進 watermark。
        """
        last = (
            GameSyncLog.objects.filter(
                status="success",
                sync_type__in=["delta", "full"],
            )
            .order_by("-created_at")
            .first()
        )
        return last.created_at if last else None

    # ─── DB records ─────────────────────────────────

    def _collect_db_records(self, since=None):
        """
        Collect all changed records using Django's built-in serializer.
        Returns (payload_dict, total_record_count, model_stats_dict).
        """
        layers_data = []
        total_count = 0
        model_stats = {}

        for layer_models in SYNC_LAYERS:
            layer_entries = []
            for item in layer_models:
                app_label, model_name, *rest = item
                extra_filter = rest[0] if rest else {}
                Model = apps.get_model(app_label, model_name)
                qs = Model.objects.filter(**extra_filter)

                # Delta filter: only changed records
                if since:
                    has_updated_at = any(
                        f.name == "updated_at" for f in Model._meta.get_fields()
                    )
                    if has_updated_at:
                        qs = qs.filter(updated_at__gt=since)
                    # Models without updated_at: always sync all (defensive fallback)

                count = qs.count()
                if count == 0:
                    continue

                # Serialize using Django's built-in serializer
                json_str = django_serializers.serialize(
                    "json",
                    qs,
                    use_natural_foreign_keys=False,
                    use_natural_primary_keys=False,
                )
                records = _strip_local_fields(f"{app_label}.{model_name}", json.loads(json_str))

                layer_entries.append(
                    {
                        "model": f"{app_label}.{model_name.lower()}",
                        "count": count,
                        "data": records,
                    }
                )
                total_count += count
                model_stats[f"{app_label}.{model_name}"] = count

            if layer_entries:
                layers_data.append(layer_entries)

        # 流程圖譯文自成一層（這張表沒有 FK，插在最前面不影響任何依賴順序）。
        text_entry = self._collect_flowchart_texts(since)
        if text_entry:
            layers_data.insert(0, [text_entry])
            total_count += text_entry["count"]
            model_stats["game.FlowchartTextTranslation"] = text_entry["count"]

        return layers_data, total_count, model_stats

    @staticmethod
    def _serialize_entry(model_label, qs):
        """把 queryset 包成 payload 的一筆 entry；沒有資料時回 None。"""
        count = qs.count()
        if count == 0:
            return None
        return {
            "model": model_label,
            "count": count,
            "data": _strip_local_fields(
                model_label, json.loads(django_serializers.serialize("json", qs)),
            ),
        }

    def _flowchart_text_hashes(self, flowchart_qs):
        """
        這批流程圖在公開頁實際會顯示到的文字 hash（含 ruleset 名稱）。

        只取公開版快照（publication.content），與公開頁
        （game/views/original_views.py）同邏輯：VPS 只顯示 reviewer 核准的版本，
        編輯中的草稿文字在 VPS 上用不到。
        """
        from game.models import FlowchartPublication
        from game.rag.flowchart.i18n import collect_texts, compute_hash

        hashes = set()
        for chart in flowchart_qs.select_related("publication"):
            try:
                pub = chart.publication
            except FlowchartPublication.DoesNotExist:
                pub = None
            if pub and pub.is_live and pub.content:
                for text in collect_texts(pub.content):
                    hashes.add(compute_hash(text))
            if chart.ruleset:
                hashes.add(compute_hash(chart.ruleset))
        return hashes

    def _flowchart_texts_for(self, flowchart_qs):
        """這批流程圖在 VPS 上在地化會用到的譯文 queryset。"""
        from game.models import FlowchartTextTranslation

        return FlowchartTextTranslation.objects.filter(
            text_hash__in=self._flowchart_text_hashes(flowchart_qs)
        )

    def _collect_flowchart_texts(self, since=None):
        """
        FlowchartTextTranslation 這次要送的批次；沒東西送時回 None。

        VPS 的公開頁是即時查這張表把流程圖在地化的（i18n.localize /
        localize_text），這批資料沒同步過去，VPS 上的圖就只會顯示原文。

        Delta 不能只看 updated_at：譯文以 sha256 去重、跨圖共用，一張圖很可能
        在譯文寫好很久之後才被核准發布，那批舊譯文的 updated_at 早於
        since 會被濾掉、之後也永遠不會再變動。所以除了「自己被改過的譯文」，
        還要補上「這次一起送出的公開版快照所引用的全部譯文」。
        公開版是否變動看 publication.updated_at：草稿被編輯不會改變 VPS 上的顯示內容。
        """
        from game.models import FlowchartTextTranslation, RulebookFlowchart

        qs = FlowchartTextTranslation.objects.all()

        if since:
            changed_charts = RulebookFlowchart.objects.published().filter(
                Q(publication__updated_at__gt=since) | Q(updated_at__gt=since),
            )
            condition = Q(updated_at__gt=since)
            hashes = self._flowchart_text_hashes(changed_charts)
            if hashes:
                condition |= Q(text_hash__in=hashes)
            qs = qs.filter(condition)

        return self._serialize_entry("game.flowcharttexttranslation", qs)

    def _send_db_records(self, token, payload, sync_type):
        """Send DB records to VPS."""
        try:
            resp = http_requests.post(
                f"{self.vps_base}/api/game/sync-data/",
                json={"sync_type": sync_type, **payload},
                headers=self._auth_headers(token),
                timeout=(10, 300),
            )
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}: {resp.text[:500]}"
            body = resp.json()
            # VPS returns 200 even on partial failure — check the result field
            if body.get("result") == "partial":
                errs = body.get("errors", [])
                summary = "; ".join(errs[:3])
                if len(errs) > 3:
                    summary += f" (+{len(errs) - 3} more)"
                return False, f"Partial save: {summary}"
            return True, body.get("message", "OK")
        except Exception as e:
            return False, str(e)

    # ─── Media files ────────────────────────────────

    def _collect_media_files(self, since=None):
        """Collect media file paths that need syncing."""
        media_root = settings.MEDIA_ROOT
        paths = []

        for prefix in MEDIA_INCLUDE_PREFIXES:
            dir_path = os.path.join(media_root, prefix)
            if not os.path.isdir(dir_path):
                continue

            for root, _dirs, files in os.walk(dir_path):
                for fname in files:
                    abs_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(abs_path, media_root)

                    # Skip excluded prefixes
                    if any(rel_path.startswith(ex) for ex in MEDIA_EXCLUDE_PREFIXES):
                        continue

                    # Delta: only files modified after since
                    if since:
                        mtime = datetime.fromtimestamp(
                            os.path.getmtime(abs_path), tz=timezone.utc
                        )
                        if mtime <= since:
                            continue

                    paths.append(abs_path)

        return paths

    def _send_media_files(self, token, file_paths):
        """
        分批打包 media 檔案上傳到 VPS，回傳 (ok, uploaded_count, message)。

        分批的理由：full sync 會送出全部檔案（目前約 130 MB），單一 POST 撐不住。
        """
        batches = self._batch_media_paths(file_paths)
        uploaded = 0
        failures = []

        for idx, batch in enumerate(batches, 1):
            ok, msg = self._send_media_batch(token, batch)
            if ok:
                uploaded += len(batch)
            else:
                failures.append(f"batch {idx}/{len(batches)} ({len(batch)} files): {msg}")

        if failures:
            summary = "; ".join(failures[:3])
            if len(failures) > 3:
                summary += f" (+{len(failures) - 3} more)"
            return False, uploaded, (
                f"Uploaded {uploaded}/{len(file_paths)} files, failed: {summary}"
            )

        return True, uploaded, f"Uploaded {uploaded} files in {len(batches)} batch(es)"

    def _batch_media_paths(self, file_paths):
        """把檔案切成每批不超過 MEDIA_BATCH_BYTES（壓縮前）的群組。"""
        batches = []
        current = []
        current_bytes = 0

        for abs_path in file_paths:
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                size = 0

            if current and current_bytes + size > MEDIA_BATCH_BYTES:
                batches.append(current)
                current = []
                current_bytes = 0

            current.append(abs_path)
            current_bytes += size

        if current:
            batches.append(current)

        return batches

    def _send_media_batch(self, token, file_paths):
        """Pack one batch into tar.gz and upload to VPS."""
        media_root = settings.MEDIA_ROOT

        try:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for abs_path in file_paths:
                    rel_path = os.path.relpath(abs_path, media_root)
                    tar.add(abs_path, arcname=rel_path)

            buf.seek(0)

            resp = http_requests.post(
                f"{self.vps_base}/api/game/sync-media/",
                files={"archive": ("media.tar.gz", buf, "application/gzip")},
                headers=self._auth_headers(token),
                # (connect, read)：urllib3 在寫出 request body 期間 socket 用的是
                # 第一個值，不是 read timeout，所以這裡必須夠長到蓋住整段上傳，
                # 否則大檔會噴 TimeoutError('The write operation timed out')。
                timeout=(MEDIA_UPLOAD_TIMEOUT, 600),
            )

            if resp.status_code == 200:
                return True, resp.json().get("message", f"Uploaded {len(file_paths)} files")
            else:
                return False, f"HTTP {resp.status_code}: {resp.text[:500]}"

        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    # ─── Qdrant delta sync (point-level upsert) ────

    def _sync_qdrant_delta(self, token, collection_name, app_label, model_name, since, sync_type, game_ids=None):
        """
        Delta sync: read ONLY changed points from local Qdrant,
        then upsert them to VPS Qdrant. Zero downtime on VPS.
        """
        qdrant_base = f"http://{self.qdrant_host}:{self.qdrant_port}"

        try:
            Model = apps.get_model(app_label, model_name)

            # Find points that need syncing
            qs = Model.objects.filter(
                vector_sync_status="synced",
                vector_point_id__isnull=False,
            )
            
            if game_ids:
                if model_name == "RulebookNode":
                    qs = qs.filter(rulebook__edition__game_id__in=game_ids)
                elif model_name == "RulebookQA":
                    qs = qs.filter(rulebook__edition__game_id__in=game_ids)

            if since and sync_type == "delta":
                qs = qs.filter(vector_synced_at__gt=since)

            point_ids = [str(pid) for pid in qs.values_list("vector_point_id", flat=True)]

            if not point_ids:
                return True, "No changed points"

            # Read points from local Qdrant in batches
            all_points = []
            for i in range(0, len(point_ids), QDRANT_BATCH_SIZE):
                batch_ids = point_ids[i : i + QDRANT_BATCH_SIZE]
                resp = http_requests.post(
                    f"{qdrant_base}/collections/{collection_name}/points",
                    json={
                        "ids": batch_ids,
                        "with_vector": True,
                        "with_payload": True,
                    },
                    timeout=(10, 60),
                )
                if resp.status_code != 200:
                    return False, f"Read points failed: HTTP {resp.status_code}"

                result = resp.json().get("result", [])
                all_points.extend(result)

            if not all_points:
                return True, "No points found in local Qdrant"

            # Send to VPS for upsert (in batches)
            upserted = 0
            for i in range(0, len(all_points), QDRANT_BATCH_SIZE):
                batch = all_points[i : i + QDRANT_BATCH_SIZE]
                resp = http_requests.post(
                    f"{self.vps_base}/api/game/sync-qdrant/{collection_name}/",
                    json={
                        "action": "upsert",
                        "points": batch,
                    },
                    headers=self._auth_headers(token),
                    timeout=(10, 300),
                )
                if resp.status_code != 200:
                    return False, f"Upsert batch failed: HTTP {resp.status_code} {resp.text[:200]}"
                upserted += len(batch)

            # Full sync: also clean up stale points on VPS
            delete_msg = ""
            if sync_type == "full":
                resp = http_requests.post(
                    f"{self.vps_base}/api/game/sync-qdrant/{collection_name}/",
                    json={
                        "action": "cleanup",
                        "valid_point_ids": point_ids,
                    },
                    headers=self._auth_headers(token),
                    timeout=(10, 300),
                )
                if resp.status_code == 200:
                    deleted = resp.json().get("deleted", 0)
                    delete_msg = f", deleted {deleted} stale"
                else:
                    delete_msg = f", cleanup failed: {resp.status_code}"

            return True, f"Upserted {upserted} points{delete_msg}"

        except Exception as e:
            return False, str(e)
