"""自訂錯誤頁（400 / 403 / 404 / 500）。

400/403/404 用 error.html，文案走 {% t %}（Translation 表）。
MESSAGES 是這些 key 的種子資料：`manage.py seed_error_translations` 會寫進 DB（只補缺的，不覆蓋已編輯的）。
500 例外：成因可能就是 DB 掛了，所以 500.html 不用 {% t %}，改由 server_error() 先試著從 DB 讀，
讀不到再退回 MESSAGES，確保錯誤頁本身不會再炸一次。

語言清單必須與 settings.LANGUAGES 一致。
這些 handler 只在 DEBUG=False 時生效（DEBUG=True 時 Django 顯示自己的除錯頁）。
"""
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import translation

MESSAGES = {
    'en': {
        'error.404.title': 'Page not found',
        'error.404.text': "We couldn't find the page you're looking for. It may have moved, or the link might be mistyped.",
        'error.500.title': 'Something went wrong',
        'error.500.text': "Something broke on our side. We've been notified — please try again in a moment.",
        'error.403.title': 'Access denied',
        'error.403.text': "You don't have permission to view this page. If you think this is a mistake, try signing in again.",
        'error.400.title': 'Bad request',
        'error.400.text': "Something about that request didn't look right, so we couldn't process it. Please go back and try again.",
        'error.btn.home': 'Back to home',
        'error.btn.games': 'Browse games',
    },
    'zh': {
        'error.404.title': '找不到這個頁面',
        'error.404.text': '你要找的頁面可能已經搬家，或是網址輸入有誤。',
        'error.500.title': '發生了一點問題',
        'error.500.text': '我們這邊出了狀況，已經收到通知。請稍後再試一次。',
        'error.403.title': '沒有權限',
        'error.403.text': '你沒有權限查看這個頁面。若你覺得這是誤判，請試著重新登入。',
        'error.400.title': '請求有誤',
        'error.400.text': '這個請求的內容有問題，我們無法處理。請回上一頁再試一次。',
        'error.btn.home': '回到首頁',
        'error.btn.games': '瀏覽遊戲',
    },
    'ja': {
        'error.404.title': 'ページが見つかりません',
        'error.404.text': 'お探しのページは移動または削除されたか、URL が間違っている可能性があります。',
        'error.500.title': '問題が発生しました',
        'error.500.text': 'サーバー側で問題が発生しました。担当者に通知されています。しばらくしてからもう一度お試しください。',
        'error.403.title': 'アクセスが拒否されました',
        'error.403.text': 'このページを表示する権限がありません。誤りだと思われる場合は、もう一度ログインしてお試しください。',
        'error.400.title': 'リクエストが正しくありません',
        'error.400.text': 'リクエストの内容に問題があり、処理できませんでした。前のページに戻ってもう一度お試しください。',
        'error.btn.home': 'ホームに戻る',
        'error.btn.games': 'ゲームを探す',
    },
    'de': {
        'error.404.title': 'Seite nicht gefunden',
        'error.404.text': 'Wir konnten die gesuchte Seite nicht finden. Sie wurde verschoben, oder der Link ist falsch geschrieben.',
        'error.500.title': 'Etwas ist schiefgelaufen',
        'error.500.text': 'Bei uns ist ein Fehler aufgetreten. Wir wurden benachrichtigt – bitte versuche es gleich noch einmal.',
        'error.403.title': 'Zugriff verweigert',
        'error.403.text': 'Du hast keine Berechtigung, diese Seite anzusehen. Falls das ein Irrtum ist, melde dich bitte erneut an.',
        'error.400.title': 'Ungültige Anfrage',
        'error.400.text': 'Mit dieser Anfrage stimmte etwas nicht, deshalb konnten wir sie nicht verarbeiten. Bitte gehe zurück und versuche es erneut.',
        'error.btn.home': 'Zur Startseite',
        'error.btn.games': 'Spiele entdecken',
    },
    'fr': {
        'error.404.title': 'Page introuvable',
        'error.404.text': "Nous n'avons pas trouvé la page demandée. Elle a peut-être été déplacée, ou le lien contient une erreur.",
        'error.500.title': "Une erreur s'est produite",
        'error.500.text': "Un problème est survenu de notre côté. Nous en avons été informés — veuillez réessayer dans un instant.",
        'error.403.title': 'Accès refusé',
        'error.403.text': "Vous n'avez pas l'autorisation de consulter cette page. Si vous pensez qu'il s'agit d'une erreur, essayez de vous reconnecter.",
        'error.400.title': 'Requête invalide',
        'error.400.text': "Cette requête comportait un problème et n'a pas pu être traitée. Veuillez revenir en arrière et réessayer.",
        'error.btn.home': "Retour à l'accueil",
        'error.btn.games': 'Parcourir les jeux',
    },
    'es': {
        'error.404.title': 'Página no encontrada',
        'error.404.text': 'No encontramos la página que buscas. Puede que se haya movido o que el enlace tenga un error.',
        'error.500.title': 'Algo salió mal',
        'error.500.text': 'Algo falló por nuestra parte. Ya fuimos notificados; inténtalo de nuevo en un momento.',
        'error.403.title': 'Acceso denegado',
        'error.403.text': 'No tienes permiso para ver esta página. Si crees que es un error, intenta iniciar sesión de nuevo.',
        'error.400.title': 'Solicitud no válida',
        'error.400.text': 'Algo en esa solicitud no era correcto y no pudimos procesarla. Vuelve atrás e inténtalo de nuevo.',
        'error.btn.home': 'Volver al inicio',
        'error.btn.games': 'Explorar juegos',
    },
}


def _lang(request):
    """request.lang 在極早期的錯誤（middleware 還沒跑）可能不存在，退回網址前綴 → en。"""
    lang = getattr(request, 'lang', None) or translation.get_language_from_path(request.path_info)
    return lang if lang in MESSAGES else 'en'


def _is_api(request):
    return request.path_info.startswith('/api/')


def _page(request, code, detail):
    if _is_api(request):
        return JsonResponse({'detail': detail}, status=code)
    ctx = {'code': code, 'title_key': 'error.%d.title' % code, 'text_key': 'error.%d.text' % code}
    return render(request, 'error.html', ctx, status=code)


def bad_request(request, exception=None):
    return _page(request, 400, 'Bad request.')


def permission_denied(request, exception=None):
    return _page(request, 403, 'Permission denied.')


def not_found(request, exception=None):
    return _page(request, 404, 'Not found.')


def server_error(request):
    # 不用 render(request, ...)：RequestContext 會跑查 DB 的 context processor。
    if _is_api(request):
        return JsonResponse({'detail': 'Server error.'}, status=500)
    lang = _lang(request)
    msg = dict(MESSAGES[lang])
    try:
        from translation.models import Translation
        msg.update(Translation.objects.filter(tribe__language=lang, key__startswith='error.')
                   .exclude(value='').values_list('key', 'value'))
    except Exception:
        pass  # DB 不可用 → 用內建文案
    ctx = {'error_lang': lang, 'title': msg['error.500.title'], 'text': msg['error.500.text'],
           'home': msg['error.btn.home']}
    return HttpResponse(render_to_string('500.html', ctx), status=500)
