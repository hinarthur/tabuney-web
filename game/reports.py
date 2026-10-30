"""
Rulesbot（AI 規則問答）與 Flowchart（流程圖）的使用數據聚合。

跟 stats/reports.py 同一個慣例：不依賴 request 的純函式，由 admin 首頁的
AdminStatsView 呼叫，日後首頁改版或換前端都能直接沿用。

兩者的資料來源完全不同：
  Rulesbot  —— game.ChatMessage，功能上線起就一直有記錄
  Flowchart —— member.UserActivity 的 flowchart_* 事件，是後來才補的前端 beacon，
               所以沒有歷史資料，只從 beacon 上線那天開始累積
"""

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

FLOWCHART_EVENTS = {
    'open': 'flowchart_open',
    'fullscreen': 'flowchart_fullscreen',
    'print': 'flowchart_print',
    'tour': 'flowchart_tour',
    'translate': 'flowchart_translate',
}

SCRIPT_EVENTS = {
    # 讀到講稿內容
    'open': 'script_open',
    # 展開了但撞到付費牆（can_view_script=False）——升級漏斗的訊號
    'locked': 'script_locked',
}


def _edition_names(edition_ids):
    """
    一次撈回 edition 的顯示名稱，避免逐筆查詢。

    命名規則沿用 game/serializers/edition_serializers.py:41 的
    `obj.name or obj.game.canonical_name`，跟搜尋結果卡片顯示的一致。
    """
    from game.models import Edition

    names = {}
    for ed in Edition.objects.filter(id__in=edition_ids).select_related('game'):
        names[str(ed.id)] = ed.name or (ed.game.canonical_name if ed.game_id else '(無遊戲)')
    return names


def _top_editions_by_meta(qs, limit):
    """把 UserActivity 事件依 meta.edition_id 分組排名，並解析成顯示名稱。"""
    rows = list(
        qs.exclude(meta__edition_id=None)
        .values('meta__edition_id')
        .annotate(total=Count('id'))
        .order_by('-total')[:limit]
    )
    names = _edition_names([r['meta__edition_id'] for r in rows])
    return [
        {
            'edition': names.get(str(r['meta__edition_id']), '(已刪除)'),
            'total': r['total'],
        }
        for r in rows
    ]


def rulesbot_insights(days=30, limit=10):
    """
    AI 規則問答的使用量。

    資料限制（解讀數字時要記得）：
      * ClearChatView 會硬刪使用者的對話，所以歷史數字可能回頭變少
      * 提問失敗或被配額擋下的都沒有記錄，「提問數」是成功數不是嘗試數
      * token 欄位在 provider 沒回報時是 null
    """
    from game.models import ChatMessage

    since = timezone.now() - timedelta(days=days)
    # role='user' 是計數謂詞，與 chat_views.get_chat_limits() 的配額計算一致。
    # 改動這裡會讓儀表板跟配額對不起來。
    questions = ChatMessage.objects.filter(role='user', created_at__gte=since)
    answers = ChatMessage.objects.filter(created_at__gte=since).exclude(role='user')

    total_questions = questions.count()
    unique_users = questions.filter(
        session__user__isnull=False
    ).values('session__user').distinct().count()
    sessions = questions.values('session').distinct().count()

    tokens = answers.aggregate(total=Sum('total_tokens'))['total'] or 0
    likes = answers.filter(feedback=ChatMessage.Feedback.LIKE).count()
    dislikes = answers.filter(feedback=ChatMessage.Feedback.DISLIKE).count()
    rated = likes + dislikes

    summary = {
        'days': days,
        'questions': total_questions,
        'unique_users': unique_users,
        'sessions': sessions,
        'avg_per_user': round(total_questions / unique_users, 1) if unique_users else 0,
        'likes': likes,
        'dislikes': dislikes,
        'satisfaction': round(likes / rated * 100, 1) if rated else None,
        'total_tokens': tokens,
    }

    rows = list(
        questions.filter(session__edition__isnull=False)
        .values('session__edition')
        .annotate(total=Count('id'))
        .order_by('-total')[:limit]
    )
    names = _edition_names([r['session__edition'] for r in rows])
    top_editions = [
        {
            'edition': names.get(str(r['session__edition']), '(已刪除)'),
            'total': r['total'],
        }
        for r in rows
    ]

    return {'summary': summary, 'top_editions': top_editions}


def flowchart_insights(days=30, limit=10):
    """
    流程圖的使用量，來自 edition 詳情頁送出的 flowchart_* beacon。

    依站方的隱私原則，beacon 只在使用者已登入時送出，所以這裡看到的
    都是會員行為，不含匿名訪客。
    """
    from member.models import UserActivity

    since = timezone.now() - timedelta(days=days)
    events = UserActivity.objects.filter(
        event_type__in=FLOWCHART_EVENTS.values(),
        created_at__gte=since,
    )

    counts = {
        row['event_type']: row['total']
        for row in events.values('event_type').annotate(total=Count('id'))
    }
    opens = events.filter(event_type=FLOWCHART_EVENTS['open'])

    summary = {
        'days': days,
        'opens': counts.get(FLOWCHART_EVENTS['open'], 0),
        'unique_users': opens.filter(
            member__isnull=False
        ).values('member').distinct().count(),
        'fullscreen': counts.get(FLOWCHART_EVENTS['fullscreen'], 0),
        'print': counts.get(FLOWCHART_EVENTS['print'], 0),
        'tour': counts.get(FLOWCHART_EVENTS['tour'], 0),
        'translate': counts.get(FLOWCHART_EVENTS['translate'], 0),
    }

    return {
        'summary': summary,
        'top_editions': _top_editions_by_meta(opens, limit),
    }


def script_insights(days=30, limit=10):
    """
    GM 講稿的使用量，來自 edition 詳情頁送出的 script_* beacon。

    講稿有付費牆（Member.can('script')），所以刻意把「讀到內容」與「撞到付費牆」
    分成兩種事件：後者是升級漏斗的訊號，前者才是功能使用量。
    """
    from member.models import UserActivity

    since = timezone.now() - timedelta(days=days)
    events = UserActivity.objects.filter(
        event_type__in=SCRIPT_EVENTS.values(),
        created_at__gte=since,
    )

    counts = {
        row['event_type']: row['total']
        for row in events.values('event_type').annotate(total=Count('id'))
    }
    opens = events.filter(event_type=SCRIPT_EVENTS['open'])
    locked = events.filter(event_type=SCRIPT_EVENTS['locked'])

    n_open = counts.get(SCRIPT_EVENTS['open'], 0)
    n_locked = counts.get(SCRIPT_EVENTS['locked'], 0)
    total = n_open + n_locked

    summary = {
        'days': days,
        'opens': n_open,
        'locked': n_locked,
        'unique_users': opens.filter(
            member__isnull=False
        ).values('member').distinct().count(),
        'locked_users': locked.filter(
            member__isnull=False
        ).values('member').distinct().count(),
        # 展開講稿的人裡有多少比例被擋在付費牆外
        'locked_rate': round(n_locked / total * 100, 1) if total else 0,
    }

    return {
        'summary': summary,
        'top_editions': _top_editions_by_meta(opens, limit),
        # 最多人想看卻看不到的講稿——直接就是升級誘因最強的內容
        'top_locked': _top_editions_by_meta(locked, limit),
    }
