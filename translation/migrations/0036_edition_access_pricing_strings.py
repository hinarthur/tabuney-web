"""Edition Access：早鳥定價文案、圖示改用真的圖示、收藏頁篩選字串。

三件事：

1. 不再用文字形容圖示。原本 membership.unlock.where / .empty 與圖例的 .def
   都寫著「bookmark-and-star / 書籤中間一顆星」——六種語言各講一套，使用者
   看完還得自己對照。改成句子結尾收在「找這個標記：」，由模板緊接著把圖示本人
   印出來（membership.html 的 .my-unlocks-marker）。

2. 加入早鳥定價：原價 US$1.99 劃掉、現價 US$1。金額字串不寫在譯文裡，改由
   settings.EDITION_ACCESS_LIST_PRICE / EDITION_ACCESS_CURRENT_PRICE 提供
   （見 game/partials/edition_access_price.html）——譯文寫死金額的話，日後
   調價要改 6 種語言 × N 個 key，而且一定會漏。所以帶金額的句子一律改寫成
   「前 3 款免費，之後每款：」這種可以直接接價格元件的收尾。

3. 收藏頁（My Collection）的 Edition Access 篩選標籤。
"""

from django.db import migrations

STRINGS = {
    # ── 早鳥定價標記 ──────────────────────────────────────────────────
    'game.unlock.price.early_supporter': {
        'en': 'Early Supporter price',
        'zh': '早鳥支持價',
        'ja': 'アーリーサポーター価格',
        'de': 'Early-Supporter-Preis',
        'fr': 'Prix Early Supporter',
        'es': 'Precio Early Supporter',
    },

    # ── info 分頁：加購區塊（金額交給價格元件，不寫進譯文）────────────
    'game.unlock.buy.offer': {
        'en': 'Your free picks are used up — get Edition Access for this edition',
        'zh': '免費名額已用完——為這個版本取得版本專享',
        'ja': '無料枠は使い切りました——このエディションのエディションアクセスを取得',
        'de': 'Deine freien Auswahlen sind aufgebraucht — hol dir Edition Access für diese Ausgabe',
        'fr': 'Vos choix gratuits sont épuisés — obtenez Edition Access pour cette édition',
        'es': 'Se acabaron tus selecciones gratuitas: consigue Edition Access para esta edición',
    },
    'game.unlock.buy.confirm': {
        'en': (
            'Get Edition Access for this edition?\n\n'
            'You will be taken to Stripe to pay. This is a one-time payment at the Early '
            'Supporter price of US$1 (normally US$1.99), not a subscription. It applies to '
            'this edition only and cannot be moved to a different game afterwards.'
        ),
        'zh': (
            '要為這個版本取得版本專享嗎？\n\n'
            '接下來會前往 Stripe 付款。這是一次性付款，目前是早鳥支持價 US$1'
            '（原價 US$1.99），不是訂閱。它只適用於這一個版本，付款後無法改成'
            '其他遊戲。'
        ),
        'ja': (
            'このエディションのエディションアクセスを取得しますか？\n\n'
            'このあと Stripe の決済画面に移動します。サブスクリプションではなく'
            '買い切りで、現在はアーリーサポーター価格の US$1（通常 US$1.99）です。'
            '対象はこのエディションだけで、購入後に別のゲームへ移すことはできません。'
        ),
        'de': (
            'Edition Access für diese Ausgabe holen?\n\n'
            'Du wirst zur Zahlung zu Stripe weitergeleitet. Es ist eine einmalige Zahlung '
            'zum Early-Supporter-Preis von 1 US$ (regulär 1,99 US$), kein Abo. Sie gilt nur '
            'für diese Ausgabe und lässt sich später nicht auf ein anderes Spiel übertragen.'
        ),
        'fr': (
            "Obtenir Edition Access pour cette édition ?\n\n"
            "Vous allez être redirigé vers Stripe pour le paiement. Il s'agit d'un paiement "
            "unique au prix Early Supporter de 1 US$ (normalement 1,99 US$), pas d'un "
            "abonnement. Il ne concerne que cette édition et ne pourra pas être transféré "
            "vers un autre jeu."
        ),
        'es': (
            '¿Conseguir Edition Access para esta edición?\n\n'
            'Te llevaremos a Stripe para pagar. Es un pago único al precio Early Supporter '
            'de 1 US$ (normalmente 1,99 US$), no una suscripción. Se aplica solo a esta '
            'edición y después no podrá pasarse a otro juego.'
        ),
    },
    'game.unlock.error.quota': {
        'en': 'Your free picks are used up. You can still get Edition Access for more editions — see the price on the game page.',
        'zh': '免費名額已用完。你仍可為其他版本取得版本專享——價格見該遊戲頁面。',
        'ja': '無料枠を使い切りました。ほかのエディションのエディションアクセスは引き続き取得できます（価格はゲームページをご覧ください）。',
        'de': 'Deine freien Auswahlen sind aufgebraucht. Edition Access für weitere Ausgaben kannst du trotzdem holen — der Preis steht auf der Spielseite.',
        'fr': "Vos choix gratuits sont épuisés. Vous pouvez toujours obtenir Edition Access pour d'autres éditions — le prix est indiqué sur la page du jeu.",
        'es': 'Se acabaron tus selecciones gratuitas. Aún puedes conseguir Edition Access para otras ediciones; el precio aparece en la página del juego.',
    },

    # ── 會員頁：句子收在「找這個標記：」，圖示由模板接著印 ────────────
    'membership.unlock.where': {
        'en': (
            'You add it from a game, not from this page: open any edition, go to its Info '
            'tab and look for this marker.'
        ),
        'zh': (
            '新增的地方在遊戲頁、不在這一頁：打開任一版本，切到「遊戲資訊」分頁，'
            '找這個標記。'
        ),
        'ja': (
            '追加はこのページからではなく、ゲーム側から行います。任意のエディションを'
            '開いて「ゲーム情報」タブに進み、このマークを探してください。'
        ),
        'de': (
            'Hinzugefügt wird er beim Spiel, nicht auf dieser Seite: Öffne eine beliebige '
            'Ausgabe, geh auf den Info-Tab und halte nach dieser Markierung Ausschau.'
        ),
        'fr': (
            "L'ajout se fait depuis un jeu, pas depuis cette page : ouvrez une édition, "
            "allez dans son onglet Infos et cherchez ce repère."
        ),
        'es': (
            'Se añade desde un juego, no desde esta página: abre cualquier edición, ve a '
            'su pestaña de Información y busca esta marca.'
        ),
    },
    'membership.unlock.pricing': {
        'en': 'Your first 3 editions are free. After that, each one is:',
        'zh': '前 3 個版本免費，之後每個版本：',
        'ja': '最初の 3 エディションは無料です。それ以降は 1 つにつき：',
        'de': 'Deine ersten 3 Ausgaben sind kostenlos. Danach kostet jede:',
        'fr': 'Vos 3 premières éditions sont gratuites. Ensuite, chacune coûte :',
        'es': 'Tus 3 primeras ediciones son gratis. Después, cada una cuesta:',
    },
    'membership.unlock.empty': {
        'en': "Nothing here yet. Open any game's Info tab to add your first one.",
        'zh': '這裡還是空的。打開任一款遊戲的「遊戲資訊」分頁，加入第一個吧。',
        'ja': 'まだ何もありません。好きなゲームの「ゲーム情報」タブから最初の 1 つを追加してください。',
        'de': 'Hier ist noch nichts. Öffne den Info-Tab eines beliebigen Spiels und füge deine erste hinzu.',
        'fr': "Rien ici pour l'instant. Ouvrez l'onglet Infos d'un jeu pour ajouter la première.",
        'es': 'Aquí todavía no hay nada. Abre la pestaña de Información de cualquier juego para añadir la primera.',
    },

    # ── 圖例：圖示就在標題旁邊，不必再用文字形容它 ────────────────────
    'game.unlock.star.def': {
        'en': (
            'On an edition you have Edition Access for, you can view its flowchart full '
            'screen, print it, walk it step by step, open every ruleset variant, and ask '
            'Rulesbot as many questions about that game as you like. It applies to that one '
            'edition and stays with your account — a subscription lapsing later does not '
            'take it away.'
        ),
        'zh': (
            '在取得版本專享的版本上，你可以全螢幕瀏覽它的流程圖、列印、逐步導覽，'
            '開啟所有 ruleset 變體，並無限次向 Rulesbot 詢問這款遊戲。它只作用於'
            '那一個版本，並且跟著你的帳號——日後會籍到期也不會被收回。'
        ),
        'ja': (
            'エディションアクセスを取得したエディションでは、フローチャートの'
            '全画面表示・印刷・ステップ導線が使え、すべてのルールセットを開けて、'
            'そのゲームについて Rulesbot に何度でも質問できます。対象はその'
            'エディション 1 つだけですが、アカウントに残り、のちにサブスクリプション'
            'が失効しても消えません。'
        ),
        'de': (
            'Bei einer Ausgabe, für die du Edition Access hast, kannst du den Ablaufplan im '
            'Vollbild ansehen, ausdrucken und Schritt für Schritt durchgehen, alle '
            'Regelvarianten öffnen und dem Rulesbot beliebig viele Fragen zu diesem Spiel '
            'stellen. Er gilt für genau diese eine Ausgabe und bleibt an deinem Konto — ein '
            'später endendes Abo nimmt ihn dir nicht weg.'
        ),
        'fr': (
            "Sur une édition pour laquelle vous avez Edition Access, vous pouvez afficher "
            "son organigramme en plein écran, l'imprimer, le parcourir pas à pas, ouvrir "
            "toutes les variantes de règles et poser autant de questions que vous voulez au "
            "Rulesbot sur ce jeu. Il concerne cette édition précise et reste attaché à votre "
            "compte : l'expiration d'un abonnement ne vous le retire pas."
        ),
        'es': (
            'En una edición para la que tienes Edition Access, puedes ver su diagrama a '
            'pantalla completa, imprimirlo, recorrerlo paso a paso, abrir todas las '
            'variantes de reglas y hacerle al Rulesbot todas las preguntas que quieras sobre '
            'ese juego. Se aplica a esa edición concreta y queda asociado a tu cuenta: que '
            'caduque una suscripción no te lo quita.'
        ),
    },

    # ── 收藏頁篩選 ────────────────────────────────────────────────────
    'game.mycollection.access_only': {
        'en': 'With Edition Access',
        'zh': '有版本專享',
        'ja': 'エディションアクセスあり',
        'de': 'Mit Edition Access',
        'fr': 'Avec Edition Access',
        'es': 'Con Edition Access',
    },
}


def add_strings(apps, schema_editor):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for key, translations in STRINGS.items():
        for lang, value in translations.items():
            tribe = Tribe.objects.filter(language=lang).first()
            if tribe is None:
                continue
            Translation.objects.update_or_create(
                tribe=tribe, key=key,
                defaults={'value': value, 'is_synced': False},
            )


def remove_strings(apps, schema_editor):
    """只刪這支新增的 key。改寫過值的舊 key 留著——倒回去也拿不回舊文字，
    刪掉反而會讓頁面直接顯示 key 本身。"""
    Translation = apps.get_model('translation', 'Translation')
    new_keys = [
        'game.unlock.price.early_supporter',
        'membership.unlock.pricing',
        'game.mycollection.access_only',
    ]
    Translation.objects.filter(key__in=new_keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0035_edition_access_rename_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
