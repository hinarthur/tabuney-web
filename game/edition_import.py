"""
「版本輸入」：把一段純文字依固定格式解析，一次建好
Game / GameTitle / Edition / Entity+EditionRole / Rulebook（與選填的縮圖）。

格式是無縮排的區段式（[game] / [edition] / [rulebook]，每行 `key: value`），
行首空白一律忽略，所以縮排打錯不影響結果。完整說明見 admin 的匯入頁。

設計原則
- 全有或全無：先把格式錯誤全部收集；通過後在單一 transaction 內執行，
  任何一個錯誤（含查無語言代碼、必填缺漏）都整批 rollback，不會加一半。
- 預覽 (commit=False) 與寫入 (commit=True) 走同一份程式碼，預覽只是最後 rollback，
  所以預覽看到的「新建 / 沿用 / 補欄位」就是實際寫入會發生的事。
- 既有資料只補空白欄位、不覆蓋。
"""
import difflib
import io
import re
from decimal import Decimal, InvalidOperation

import requests
from django.core.files.base import ContentFile
from django.db import transaction

from .models import (
    Edition, EditionRole, Entity, Game, GameTitle, Rulebook,
)
from .utils import image_to_webp_bytes
from commerce.models import Currency
from translation.models import Region, Tribe


# ---------------------------------------------------------------------------
# 格式定義
# ---------------------------------------------------------------------------

GAME_KEYS = {
    "name", "bgg_id", "kind", "parent", "players", "playtime", "title",
}
EDITION_KEYS = {
    "name", "language", "packaging_language", "region", "release_year",
    "barcode", "age", "msrp", "primary", "thumbnail", "summary",
    "publisher", "designer", "artist",
}
RULEBOOK_KEYS = {"title", "language", "url"}
SECTION_KEYS = {"game": GAME_KEYS, "edition": EDITION_KEYS, "rulebook": RULEBOOK_KEYS}

# 可以重複寫多行的 key
REPEATABLE = {
    "game": {"title"},
    "edition": {"packaging_language", "publisher", "designer", "artist"},
    "rulebook": set(),
}

ROLE_ENTITY_TYPE = {"publisher": "company", "designer": "individual", "artist": "individual"}

SECTION_RE = re.compile(r"^\[\s*(\w+)\s*\]$")
RANGE_RE = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")
MSRP_RE = re.compile(r"^(\d+(?:\.\d+)?)\s+([A-Za-z]{3})$")
MAX_IMAGE_BYTES = 15 * 1024 * 1024


class Block:
    """一個區段：fields 是 key -> [(value, line)]。"""

    def __init__(self, kind, line):
        self.kind = kind
        self.line = line
        self.fields = {}
        self.children = []   # game -> edition blocks；edition -> rulebook blocks

    def one(self, key):
        vals = self.fields.get(key)
        return vals[0][0] if vals else ""

    def line_of(self, key):
        vals = self.fields.get(key)
        return vals[0][1] if vals else self.line

    def many(self, key):
        return self.fields.get(key, [])


class Report:
    def __init__(self):
        self.items = []   # dict(level, depth, line, text)

    def add(self, level, text, line=None, depth=0):
        self.items.append({"level": level, "depth": depth, "line": line, "text": text})

    def error(self, text, line=None, depth=0):
        self.add("error", text, line, depth)

    @property
    def errors(self):
        return [i for i in self.items if i["level"] == "error"]

    @property
    def warnings(self):
        return [i for i in self.items if i["level"] == "warn"]

    @property
    def has_errors(self):
        return any(i["level"] == "error" for i in self.items)


# ---------------------------------------------------------------------------
# 解析（只檢查格式，不碰資料庫）
# ---------------------------------------------------------------------------

def parse(text, rep):
    """回傳 game Block 清單（children 內含 edition，再內含 rulebook）。格式錯誤寫入 rep。"""
    games = []
    cur_game = cur_edition = cur = None
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        lineno = i + 1
        raw = lines[i].strip()
        i += 1
        if not raw or raw.startswith("#"):
            continue

        m = SECTION_RE.match(raw)
        if m:
            kind = m.group(1).lower()
            if kind not in SECTION_KEYS:
                rep.error(f"未知的區段 [{m.group(1)}]（只有 [game] [edition] [rulebook]）", lineno)
                cur = None
                continue
            block = Block(kind, lineno)
            if kind == "game":
                games.append(block)
                cur_game, cur_edition = block, None
            elif kind == "edition":
                if cur_game is None:
                    rep.error("[edition] 前面沒有 [game]", lineno)
                    cur = None
                    continue
                cur_game.children.append(block)
                cur_edition = block
            else:
                if cur_edition is None:
                    rep.error("[rulebook] 前面沒有 [edition]", lineno)
                    cur = None
                    continue
                cur_edition.children.append(block)
            cur = block
            continue

        if ":" not in raw:
            rep.error(f"無法辨識的行（需要 `key: value`）：{raw[:40]}", lineno)
            continue
        if cur is None:
            rep.error("這一行不屬於任何區段（前面缺少有效的 [game]/[edition]/[rulebook]）", lineno)
            continue

        key, value = raw.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()

        if key not in SECTION_KEYS[cur.kind]:
            rep.error(f"[{cur.kind}] 沒有「{key}」這個欄位（是不是打錯字？）", lineno)
            continue

        if value == "<<<":
            buf = []
            closed = False
            start = lineno
            while i < len(lines):
                if lines[i].strip() == ">>>":
                    closed = True
                    i += 1
                    break
                buf.append(lines[i].strip())
                i += 1
            if not closed:
                rep.error("`<<<` 沒有對應的 `>>>`", start)
                continue
            value = "\n".join(buf).strip()

        if key in cur.fields and key not in REPEATABLE[cur.kind]:
            rep.error(f"「{key}」在同一個 [{cur.kind}] 重複出現了", lineno)
            continue
        if value:
            cur.fields.setdefault(key, []).append((value, lineno))

    if not games and not rep.has_errors:
        rep.error("沒有任何 [game] 區段")
    return games


# ---------------------------------------------------------------------------
# 欄位轉型
# ---------------------------------------------------------------------------

def _int(block, key, rep, depth):
    v = block.one(key)
    if not v:
        return None
    if not v.isdigit():
        rep.error(f"「{key}」必須是整數：{v}", block.line_of(key), depth)
        return None
    return int(v)


def _range(block, key, rep, depth):
    v = block.one(key)
    if not v:
        return None, None
    m = RANGE_RE.match(v)
    if not m:
        rep.error(f"「{key}」格式應為 `3-4` 或 `2`：{v}", block.line_of(key), depth)
        return None, None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    if hi < lo:
        rep.error(f"「{key}」最大值小於最小值：{v}", block.line_of(key), depth)
        return None, None
    return lo, hi


def _bool(block, key, rep, depth):
    v = block.one(key).lower()
    if not v:
        return None
    if v in ("yes", "true", "1", "y"):
        return True
    if v in ("no", "false", "0", "n"):
        return False
    rep.error(f"「{key}」請寫 yes 或 no：{v}", block.line_of(key), depth)
    return None


def _tribe(code, line, rep, depth):
    code = (code or "").strip().lower()
    tribe = Tribe.objects.filter(language__iexact=code).first() if code else None
    if tribe is None:
        rep.error(f"語言代碼「{code}」在 Tribe 裡找不到", line, depth)
    return tribe


def _fill(obj, values, labels=None):
    """只補空白：obj 欄位為 None / '' 才寫入。回傳 (實際補的欄位, 被略過的欄位)。"""
    filled, skipped = [], []
    for field, new in values.items():
        if new in (None, ""):
            continue
        cur = getattr(obj, field)
        if cur in (None, ""):
            setattr(obj, field, new)
            filled.append(field)
        elif cur != new:
            skipped.append(f"{field}（現有 {cur}，輸入 {new}，保留現有）")
    return filled, skipped


# ---------------------------------------------------------------------------
# Entity 相似名稱偵測
# ---------------------------------------------------------------------------

def _norm(name):
    return re.sub(r"[\W_]+", "", name.lower())


class _EntityNames:
    def __init__(self):
        self._names = None

    def similar(self, name):
        if self._names is None:
            self._names = list(Entity.objects.values_list("name", flat=True))
        target = _norm(name)
        if len(target) < 3:
            return []
        by_norm = {_norm(n): n for n in self._names}
        hits = difflib.get_close_matches(target, list(by_norm), n=3, cutoff=0.85)
        return [by_norm[h] for h in hits]

    def add(self, name):
        if self._names is not None:
            self._names.append(name)


# ---------------------------------------------------------------------------
# 縮圖
# ---------------------------------------------------------------------------

def _fetch_thumbnail(url):
    """下載並轉成 400px WebP bytes；失敗丟 ValueError。"""
    from PIL import Image
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        data = resp.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
    except Exception as e:
        raise ValueError(f"下載失敗：{e}")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("圖檔超過 15MB")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            return image_to_webp_bytes(img)
    except Exception as e:
        raise ValueError(f"不是有效的圖片：{e}")


# ---------------------------------------------------------------------------
# 執行
# ---------------------------------------------------------------------------

class _Rollback(Exception):
    pass


def run_import(text, commit):
    """
    解析並執行。commit=False 只預覽（最後一律 rollback）；commit=True 且沒有任何錯誤才真的寫入。
    回傳 Report。
    """
    rep = Report()
    games = parse(text, rep)
    if rep.has_errors:
        return rep

    saved_files = []
    pending_thumbs = []   # (edition, webp bytes, line)
    names = _EntityNames()
    try:
        with transaction.atomic():
            for gb in games:
                _do_game(gb, rep, commit, pending_thumbs, names)

            if commit and not rep.has_errors:
                for edition, data, line in pending_thumbs:
                    edition.thumbnail_optimized = True
                    edition.thumbnail.save("thumb.webp", ContentFile(data), save=True)
                    saved_files.append(edition.thumbnail)
            if rep.has_errors or not commit:
                raise _Rollback()
    except _Rollback:
        pass
    except Exception as e:   # IntegrityError 等：整批已還原，把圖檔也清掉
        rep.error(f"寫入失敗，已全部還原：{e}")
    if rep.has_errors:
        for f in saved_files:
            try:
                f.storage.delete(f.name)
            except Exception:
                pass
    return rep


def _find_game(ref):
    """ref 是 bgg_id（純數字）或名稱。"""
    if ref.isdigit():
        g = Game.objects.filter(bgg_id=int(ref)).first()
        if g:
            return g
    qs = Game.objects.filter(canonical_name__iexact=ref)
    return qs.first() if qs.count() == 1 else None


def _do_game(gb, rep, commit, pending_thumbs, names):
    n0 = len(rep.errors)
    name = gb.one("name")
    if not name:
        rep.error("[game] 缺少必填欄位 name", gb.line)
        return

    bgg_id = _int(gb, "bgg_id", rep, 0)
    kind = gb.one("kind").lower()
    if kind and kind not in dict(Game.Kind.choices):
        rep.error(f"kind 必須是 {', '.join(dict(Game.Kind.choices))}：{kind}", gb.line_of("kind"))
    min_p, max_p = _range(gb, "players", rep, 0)
    min_t, max_t = _range(gb, "playtime", rep, 0)

    parent = None
    if gb.one("parent"):
        parent = _find_game(gb.one("parent"))
        if parent is None:
            rep.error(f"找不到主遊戲 parent：{gb.one('parent')}（若同一份輸入建立，請寫在它後面）",
                      gb.line_of("parent"))

    titles = []
    for raw, line in gb.many("title"):
        if "|" not in raw:
            rep.error("title 格式應為 `語言代碼 | 標題`", line)
            continue
        code, title = (s.strip() for s in raw.split("|", 1))
        primary = title.endswith("*")
        title = title.rstrip("*").strip()
        tribe = _tribe(code, line, rep, 0)
        if not title:
            rep.error("title 的標題是空的", line)
        if tribe and title:
            titles.append((tribe, title, primary))

    if len(rep.errors) > n0:
        return

    # --- 比對 / 建立 Game ---
    game = None
    if bgg_id is not None:
        game = Game.objects.filter(bgg_id=bgg_id).first()
        if game and game.canonical_name.lower() != name.lower():
            rep.add("warn", f"bgg_id {bgg_id} 對到的遊戲名稱是「{game.canonical_name}」，與輸入的「{name}」不同",
                    gb.line)
    if game is None:
        qs = Game.objects.filter(canonical_name__iexact=name)
        count = qs.count()
        if count > 1:
            rep.error(f"有 {count} 個遊戲叫「{name}」，無法判斷是哪一個（請填 bgg_id）", gb.line)
            return
        game = qs.first()

    values = {
        "bgg_id": bgg_id, "kind": kind or None, "min_players": min_p, "max_players": max_p,
        "min_playtime": min_t, "max_playtime": max_t, "parent_game": parent,
    }
    if game is None:
        game = Game(canonical_name=name, **{k: v for k, v in values.items() if v is not None})
        game.save()
        rep.add("new", f"Game 新建：{name}", gb.line)
    else:
        filled, skipped = _fill(game, values)
        if filled:
            game.save()
            rep.add("fill", f"Game 沿用「{game.canonical_name}」，補欄位：{', '.join(filled)}", gb.line)
        else:
            rep.add("same", f"Game 沿用「{game.canonical_name}」", gb.line)
        for s in skipped:
            rep.add("skip", f"略過 {s}", gb.line, 1)

    for tribe, title, primary in titles:
        _do_title(game, tribe, title, primary, gb.line, rep)

    for eb in gb.children:
        _do_edition(game, eb, rep, commit, pending_thumbs, names)


def _do_title(game, tribe, title, primary, line, rep):
    has_primary = game.titles.filter(is_primary=True).exists()
    obj, created = GameTitle.objects.get_or_create(
        game=game, language=tribe, title=title,
        defaults={"is_primary": primary and not has_primary},
    )
    if created:
        rep.add("new", f"GameTitle 新建：{tribe.language} | {title}", line, 1)
    else:
        rep.add("same", f"GameTitle 沿用：{tribe.language} | {title}", line, 1)
    if primary and has_primary and not obj.is_primary:
        rep.add("warn", f"「{title}」標了 * 但這個遊戲已有主要標題，未更動", line, 1)
    elif primary and not has_primary and not obj.is_primary:
        obj.is_primary = True
        obj.save(update_fields=["is_primary", "updated_at"])


def _do_edition(game, eb, rep, commit, pending_thumbs, names):
    n0 = len(rep.errors)
    d = 1
    name = eb.one("name")
    year = _int(eb, "release_year", rep, d)
    for key in ("name", "language", "release_year"):
        if not eb.one(key):
            rep.error(f"[edition] 缺少必填欄位 {key}", eb.line, d)

    language = _tribe(eb.one("language"), eb.line_of("language"), rep, d) if eb.one("language") else None
    pack_langs = [t for t in (_tribe(v, ln, rep, d) for v, ln in eb.many("packaging_language")) if t]

    region = None
    if eb.one("region"):
        region = Region.objects.filter(code__iexact=eb.one("region")).first()
        if region is None:
            rep.error(f"地區代碼「{eb.one('region')}」在 Region 裡找不到", eb.line_of("region"), d)

    age = _int(eb, "age", rep, d)
    primary = _bool(eb, "primary", rep, d)

    msrp = currency = None
    if eb.one("msrp"):
        m = MSRP_RE.match(eb.one("msrp"))
        if not m:
            rep.error(f"msrp 格式應為 `金額 幣別碼`，例如 1280 TWD：{eb.one('msrp')}", eb.line_of("msrp"), d)
        else:
            try:
                msrp = Decimal(m.group(1))
            except InvalidOperation:
                rep.error(f"msrp 金額無效：{m.group(1)}", eb.line_of("msrp"), d)
            currency = Currency.objects.filter(code__iexact=m.group(2)).first()
            if currency is None:
                rep.error(f"幣別代碼「{m.group(2)}」在 Currency 裡找不到", eb.line_of("msrp"), d)

    thumb_url = eb.one("thumbnail")
    if thumb_url and not thumb_url.lower().startswith(("http://", "https://")):
        rep.error(f"thumbnail 必須是 http(s) 網址：{thumb_url}", eb.line_of("thumbnail"), d)
        thumb_url = ""

    barcode = eb.one("barcode") or None

    if len(rep.errors) > n0:
        return

    # --- 比對 Edition ---
    label = f"{name} ({year})"
    existing = Edition.objects.filter(game=game, name=name, release_year=year).first()
    if existing and existing.language_id != language.pk:
        cur = existing.language.language if existing.language else "無"
        rep.error(f"Edition「{label}」已存在，但語言不同（現有 {cur}，輸入 {language.language}）。"
                  f"若是不同版本請改 name", eb.line, d)
        return
    if barcode:
        other = Edition.objects.filter(barcode=barcode)
        if existing:
            other = other.exclude(pk=existing.pk)
        clash = other.first()
        if clash:
            rep.error(f"條碼 {barcode} 已屬於另一個 Edition：{clash.game} / {clash.name}", eb.line_of("barcode"), d)
            return
    if not existing:
        siblings = list(Edition.objects.filter(game=game, name=name).values_list("release_year", flat=True))
        if siblings:
            rep.add("warn", f"此遊戲已有同名「{name}」但年份不同（{', '.join(map(str, siblings))}），將新建一筆", eb.line, d)

    values = {
        "region": region, "barcode": barcode, "age": age, "msrp": msrp, "msrp_currency": currency,
        "summary": eb.one("summary"),
    }
    if existing is None:
        edition = Edition(
            game=game, name=name, release_year=year, language=language,
            is_primary=bool(primary),
            **{k: v for k, v in values.items() if v not in (None, "")},
        )
        edition.save()
        rep.add("new", f"Edition 新建：{label} [{language.language}]", eb.line, d)
    else:
        edition = existing
        filled, skipped = _fill(edition, values)
        if filled:
            edition.save()
            rep.add("fill", f"Edition 沿用「{label}」，補欄位：{', '.join(filled)}", eb.line, d)
        else:
            rep.add("same", f"Edition 沿用「{label}」", eb.line, d)
        for s in skipped:
            rep.add("skip", f"略過 {s}", eb.line, d + 1)
        if primary is not None and primary != edition.is_primary:
            rep.add("skip", f"略過 is_primary（現有 {edition.is_primary}，輸入 {primary}，保留現有）", eb.line, d + 1)

    # packaging_languages：只新增不移除。M2M 寫的是中介表，不會觸發 Edition 的 auto_now，
    # delta sync 只看 updated_at，所以真的有新增時要手動 touch，否則這筆變更不會被同步。
    have = set(edition.packaging_languages.values_list("pk", flat=True))
    added = [t for t in pack_langs if t.pk not in have]
    if added:
        edition.packaging_languages.add(*added)
        from django.utils import timezone
        Edition.objects.filter(pk=edition.pk).update(updated_at=timezone.now())
        rep.add("fill", f"packaging_languages 新增：{', '.join(t.language for t in added)}", eb.line, d + 1)

    # 縮圖：只在沒有圖時處理
    if thumb_url:
        if edition.thumbnail:
            rep.add("skip", "已有縮圖，略過 thumbnail", eb.line_of("thumbnail"), d + 1)
        elif not commit:
            rep.add("fill", "將下載縮圖並轉成 400px WebP（預覽不下載）", eb.line_of("thumbnail"), d + 1)
        else:
            try:
                pending_thumbs.append((edition, _fetch_thumbnail(thumb_url), eb.line_of("thumbnail")))
                rep.add("fill", "縮圖已下載並轉成 400px WebP", eb.line_of("thumbnail"), d + 1)
            except ValueError as e:
                rep.error(f"縮圖 {e}", eb.line_of("thumbnail"), d + 1)

    # 出版 / 設計 / 美術
    for role, etype in ROLE_ENTITY_TYPE.items():
        for ename, line in eb.many(role):
            _do_role(edition, role, etype, ename, line, rep, names)

    for rb in eb.children:
        _do_rulebook(edition, rb, rep)


def _do_role(edition, role, etype, ename, line, rep, names):
    matches = list(Entity.objects.filter(name__iexact=ename)[:2])
    if len(matches) > 1:
        rep.error(f"有多個 Entity 名稱與「{ename}」只差大小寫，無法判斷", line, 2)
        return
    if matches:
        entity = matches[0]
    else:
        similar = names.similar(ename)
        entity = Entity.objects.create(name=ename, entity_type=etype)
        names.add(ename)
        rep.add("new", f"Entity 新建：{ename}（{etype}）", line, 2)
        if similar:
            rep.add("warn", f"「{ename}」與既有 Entity 很像：{'、'.join(similar)}，請確認是不是打錯字", line, 3)
    _, created = EditionRole.objects.get_or_create(edition=edition, entity=entity, role=role)
    rep.add("new" if created else "same", f"{role}：{entity.name}", line, 2)


def _do_rulebook(edition, rb, rep):
    n0 = len(rep.errors)
    d = 2
    url = rb.one("url")
    if not url:
        rep.error("[rulebook] 缺少必填欄位 url", rb.line, d)
    elif not url.lower().startswith(("http://", "https://")):
        rep.error(f"url 必須是 http(s) 網址：{url}", rb.line_of("url"), d)
    if not rb.one("language"):
        rep.error("[rulebook] 缺少必填欄位 language", rb.line, d)
        language = None
    else:
        language = _tribe(rb.one("language"), rb.line_of("language"), rep, d)
    if len(rep.errors) > n0:
        return

    title = rb.one("title") or "Rulebook"
    obj, created = Rulebook.objects.get_or_create(
        edition=edition, language=language, source_url=url,
        defaults={"title": title},
    )
    rep.add("new" if created else "same",
            f"Rulebook {'新建' if created else '沿用'}：{obj.title} [{language.language}]", rb.line, d)
