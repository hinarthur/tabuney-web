"""Edition Access（版本專享）：功能改名 + 兩段不同的免費名額確認文字。

三件事：

1. 功能定名為「Edition Access / 版本專享」。原本的文案一直用「permanently
   unlocked」這種描述而不是名字，使用者在會員頁與 info 頁看到的是兩套說法。
   'Edition Access' 當作產品名保留原文（de/fr/es 慣例上不翻產品名），zh 用
   「版本專享」，ja 用片假名。

2. 免費名額的確認文字拆成兩段。原本不論該版本有沒有流程圖都講「選定後不可
   變更」，但對還沒有流程圖的版本那是錯的——那種情況名額退得回來。兩種後果
   不同就該用兩段文字。

3. 會員頁的標題不再用 permanently / unlocked，改成功能名本身，並補上兩段
   說明：這是什麼、以及要去各 edition 的 info 分頁取得（那一頁沒有新增入口）。

update_or_create 會覆寫既有值，所以舊 key 直接沿用、不另開新 key——key 名稱
是內部識別，改名只改顯示文字。
"""

from django.db import migrations

# 產品名：拉丁語系保留原文，zh/ja 有自己的說法
NAME = {
    'en': 'Edition Access',
    'zh': '版本專享',
    'ja': 'エディションアクセス',
    'de': 'Edition Access',
    'fr': 'Edition Access',
    'es': 'Edition Access',
}

STRINGS = {
    # ── 功能名稱與圖例 ────────────────────────────────────────────────
    'game.unlock.star': dict(NAME),
    'game.unlock.star.def': {
        'en': (
            'Edition Access is marked with a bookmark-and-star. On an edition you have '
            'it for, you can view its flowchart full screen, print it, walk it step by '
            'step, open every ruleset variant, and ask Rulesbot as many questions about '
            'that game as you like. It applies to that one edition and stays with your '
            'account — a subscription lapsing later does not take it away.'
        ),
        'zh': (
            '版本專享以「書籤中間一顆星」標示。在取得版本專享的版本上，你可以全螢幕'
            '瀏覽它的流程圖、列印、逐步導覽，開啟所有 ruleset 變體，並無限次向 '
            'Rulesbot 詢問這款遊戲。它只作用於那一個版本，並且跟著你的帳號——日後'
            '會籍到期也不會被收回。'
        ),
        'ja': (
            'エディションアクセスは「しおりの中央に星」のマークで示されます。'
            '対象のエディションでは、フローチャートの全画面表示・印刷・ステップ導線が'
            '使え、すべてのルールセットを開けて、そのゲームについて Rulesbot に'
            '何度でも質問できます。対象はそのエディション 1 つだけですが、'
            'アカウントに残り、のちにサブスクリプションが失効しても消えません。'
        ),
        'de': (
            'Edition Access wird mit einem Lesezeichen samt Stern gekennzeichnet. Bei '
            'einer Ausgabe, für die du ihn hast, kannst du den Ablaufplan im Vollbild '
            'ansehen, ausdrucken und Schritt für Schritt durchgehen, alle Regelvarianten '
            'öffnen und dem Rulesbot beliebig viele Fragen zu diesem Spiel stellen. Er '
            'gilt für genau diese eine Ausgabe und bleibt an deinem Konto — ein später '
            'endendes Abo nimmt ihn dir nicht weg.'
        ),
        'fr': (
            "Edition Access est signalé par un marque-page avec une étoile. Sur une "
            "édition pour laquelle vous l'avez, vous pouvez afficher son organigramme en "
            "plein écran, l'imprimer, le parcourir pas à pas, ouvrir toutes les variantes "
            "de règles et poser autant de questions que vous voulez au Rulesbot sur ce "
            "jeu. Il concerne cette édition précise et reste attaché à votre compte : "
            "l'expiration d'un abonnement ne vous le retire pas."
        ),
        'es': (
            'Edition Access se indica con un marcador que lleva una estrella. En una '
            'edición para la que lo tienes, puedes ver su diagrama a pantalla completa, '
            'imprimirlo, recorrerlo paso a paso, abrir todas las variantes de reglas y '
            'hacerle al Rulesbot todas las preguntas que quieras sobre ese juego. Se '
            'aplica a esa edición concreta y queda asociado a tu cuenta: que caduque una '
            'suscripción no te lo quita.'
        ),
    },

    # ── 各狀態的標題 ──────────────────────────────────────────────────
    'game.unlock.picked': {
        'en': 'Edition Access · active',
        'zh': '已取得版本專享',
        'ja': 'エディションアクセス取得済み',
        'de': 'Edition Access · aktiv',
        'fr': 'Edition Access · actif',
        'es': 'Edition Access · activo',
    },
    'game.unlock.login': {
        'en': 'Sign in to claim Edition Access for 3 games, free.',
        'zh': '登入即可免費為 3 款遊戲取得版本專享。',
        'ja': 'ログインすると、3 つのゲームのエディションアクセスを無料で取得できます。',
        'de': 'Melde dich an und sichere dir Edition Access für 3 Spiele – kostenlos.',
        'fr': 'Connectez-vous pour obtenir gratuitement Edition Access sur 3 jeux.',
        'es': 'Inicia sesión para obtener gratis Edition Access en 3 juegos.',
    },
    'game.unlock.pick.offer': {
        'en': 'Claim Edition Access for this edition, free',
        'zh': '免費取得這個版本的版本專享',
        'ja': 'このエディションのエディションアクセスを無料で取得',
        'de': 'Edition Access für diese Ausgabe kostenlos sichern',
        'fr': 'Obtenez gratuitement Edition Access pour cette édition',
        'es': 'Obtén gratis Edition Access para esta edición',
    },
    'game.unlock.buy.offer': {
        'en': 'Your free picks are used up — get Edition Access for this edition for US$1',
        'zh': '免費名額已用完——US$1 即可取得這個版本的版本專享',
        'ja': '無料枠は使い切りました——US$1 でこのエディションのエディションアクセスを取得',
        'de': 'Deine freien Auswahlen sind aufgebraucht — Edition Access für diese Ausgabe für 1 US$',
        'fr': 'Vos choix gratuits sont épuisés — obtenez Edition Access pour cette édition pour 1 US$',
        'es': 'Se acabaron tus selecciones gratuitas: consigue Edition Access para esta edición por 1 US$',
    },
    'game.unlock.buy': {
        'en': 'Get Edition Access',
        'zh': '取得版本專享',
        'ja': 'エディションアクセスを取得',
        'de': 'Edition Access holen',
        'fr': 'Obtenir Edition Access',
        'es': 'Obtener Edition Access',
    },
    'game.unlock.success': {
        'en': 'Done. Edition Access for this edition is on your account.',
        'zh': '完成。這個版本的版本專享已記在你的帳號上。',
        'ja': '完了しました。このエディションのエディションアクセスがアカウントに追加されました。',
        'de': 'Fertig. Edition Access für diese Ausgabe liegt jetzt auf deinem Konto.',
        'fr': "C'est fait. Edition Access pour cette édition est associé à votre compte.",
        'es': 'Listo. Edition Access para esta edición está en tu cuenta.',
    },

    # ── 免費名額確認：該版本已有流程圖（＝這一選就定案）──────────────
    'game.unlock.confirm': {
        'en': (
            'Use one of your free picks on this edition?\n\n'
            'This edition already has a published flowchart, so the pick is final — it '
            'cannot be moved to another game afterwards.'
        ),
        'zh': (
            '要用一個免費名額取得這個版本的版本專享嗎？\n\n'
            '這個版本已經有已發布的流程圖，所以這一選即為定案，日後無法改到其他遊戲。'
        ),
        'ja': (
            '無料枠を 1 つ使って、このエディションのエディションアクセスを取得しますか？\n\n'
            'このエディションには公開済みのフローチャートが既にあるため、この選択は'
            '確定となり、あとから別のゲームへ移すことはできません。'
        ),
        'de': (
            'Eine deiner freien Auswahlen für diese Ausgabe einsetzen?\n\n'
            'Zu dieser Ausgabe ist bereits ein Ablaufplan veröffentlicht, die Auswahl ist '
            'damit endgültig und lässt sich später nicht auf ein anderes Spiel übertragen.'
        ),
        'fr': (
            "Utiliser l'un de vos choix gratuits sur cette édition ?\n\n"
            "Cette édition a déjà un organigramme publié : le choix est donc définitif et "
            "ne pourra pas être transféré vers un autre jeu."
        ),
        'es': (
            '¿Usar una de tus selecciones gratuitas en esta edición?\n\n'
            'Esta edición ya tiene un diagrama publicado, así que la selección es '
            'definitiva y después no podrá pasarse a otro juego.'
        ),
    },

    # ── 免費名額確認：該版本尚無流程圖（＝可以先佔著，隨時退回）──────
    'game.unlock.confirm.no_flowchart': {
        'en': (
            'Use one of your free picks on this edition?\n\n'
            'No flowchart is published for this edition yet. You can claim it now and '
            'Edition Access will apply the moment one goes live — and until that happens '
            'you can take the pick back and use it on another game.'
        ),
        'zh': (
            '要用一個免費名額取得這個版本的版本專享嗎？\n\n'
            '這個版本目前還沒有已發布的流程圖。你可以先選起來，流程圖一上線就自動'
            '生效；在那之前，你隨時可以把名額退回改選其他遊戲。'
        ),
        'ja': (
            '無料枠を 1 つ使って、このエディションのエディションアクセスを取得しますか？\n\n'
            'このエディションにはまだ公開済みのフローチャートがありません。先に'
            '確保しておけば、公開された時点で自動的に有効になります。それまでは'
            'いつでも枠を戻して別のゲームに使えます。'
        ),
        'de': (
            'Eine deiner freien Auswahlen für diese Ausgabe einsetzen?\n\n'
            'Zu dieser Ausgabe ist noch kein Ablaufplan veröffentlicht. Du kannst sie '
            'jetzt schon wählen — Edition Access greift, sobald einer erscheint. Bis '
            'dahin kannst du die Auswahl jederzeit zurücknehmen und für ein anderes Spiel '
            'verwenden.'
        ),
        'fr': (
            "Utiliser l'un de vos choix gratuits sur cette édition ?\n\n"
            "Aucun organigramme n'est encore publié pour cette édition. Vous pouvez la "
            "réserver dès maintenant : Edition Access s'appliquera dès qu'un organigramme "
            "sera mis en ligne, et d'ici là vous pouvez récupérer votre choix pour "
            "l'utiliser sur un autre jeu."
        ),
        'es': (
            '¿Usar una de tus selecciones gratuitas en esta edición?\n\n'
            'Esta edición aún no tiene ningún diagrama publicado. Puedes reservarla ahora '
            'y Edition Access se activará en cuanto se publique uno; hasta entonces '
            'puedes recuperar la selección y usarla en otro juego.'
        ),
    },
    'game.unlock.pick.no_flowchart_hint': {
        'en': (
            'No flowchart is published for this edition yet. Claim it now and you can '
            'still take the pick back at any time before one goes live.'
        ),
        'zh': (
            '這個版本還沒有已發布的流程圖。現在選起來，在流程圖上線之前你仍可隨時'
            '退回名額。'
        ),
        'ja': (
            'このエディションにはまだ公開済みのフローチャートがありません。今'
            '確保しても、公開されるまではいつでも枠を戻せます。'
        ),
        'de': (
            'Zu dieser Ausgabe ist noch kein Ablaufplan veröffentlicht. Du kannst sie '
            'jetzt wählen und die Auswahl bis zur Veröffentlichung jederzeit zurücknehmen.'
        ),
        'fr': (
            "Aucun organigramme n'est encore publié pour cette édition. Réservez-la "
            "maintenant : vous pourrez récupérer votre choix à tout moment avant sa mise "
            "en ligne."
        ),
        'es': (
            'Esta edición aún no tiene ningún diagrama publicado. Resérvala ahora y '
            'podrás recuperar la selección en cualquier momento antes de que se publique.'
        ),
    },

    # ── 會員頁 ────────────────────────────────────────────────────────
    'membership.unlock.heading': {
        'en': 'My Edition Access',
        'zh': '我的版本專享',
        'ja': 'マイ・エディションアクセス',
        'de': 'Mein Edition Access',
        'fr': 'Mon Edition Access',
        'es': 'Mi Edition Access',
    },
    'membership.unlock.intro': {
        'en': (
            'Edition Access is tied to a single edition of a game. On an edition you have '
            'it for, you can view its flowchart full screen, print it, walk it step by '
            'step, open every ruleset variant, and ask Rulesbot as many questions about '
            'that game as you like. It stays with your account — a subscription ending '
            'later does not take it away.'
        ),
        'zh': (
            '版本專享是綁在單一遊戲版本上的。在取得版本專享的版本上，你可以全螢幕'
            '瀏覽它的流程圖、列印、逐步導覽，開啟所有 ruleset 變體，並無限次向 '
            'Rulesbot 詢問這款遊戲。它會跟著你的帳號——日後會籍結束也不會被收回。'
        ),
        'ja': (
            'エディションアクセスはゲームの特定のエディションに紐づきます。対象の'
            'エディションでは、フローチャートの全画面表示・印刷・ステップ導線が使え、'
            'すべてのルールセットを開けて、そのゲームについて Rulesbot に何度でも'
            '質問できます。アカウントに残るので、のちにサブスクリプションが終了しても'
            '失われません。'
        ),
        'de': (
            'Edition Access hängt jeweils an einer einzelnen Ausgabe eines Spiels. Bei '
            'einer Ausgabe, für die du ihn hast, kannst du den Ablaufplan im Vollbild '
            'ansehen, ausdrucken und Schritt für Schritt durchgehen, alle Regelvarianten '
            'öffnen und dem Rulesbot beliebig viele Fragen zu diesem Spiel stellen. Er '
            'bleibt an deinem Konto — ein später endendes Abo nimmt ihn dir nicht weg.'
        ),
        'fr': (
            "Edition Access est rattaché à une seule édition d'un jeu. Sur une édition "
            "pour laquelle vous l'avez, vous pouvez afficher son organigramme en plein "
            "écran, l'imprimer, le parcourir pas à pas, ouvrir toutes les variantes de "
            "règles et poser autant de questions que vous voulez au Rulesbot sur ce jeu. "
            "Il reste attaché à votre compte : la fin d'un abonnement ne vous le retire pas."
        ),
        'es': (
            'Edition Access va ligado a una sola edición de un juego. En una edición para '
            'la que lo tienes, puedes ver su diagrama a pantalla completa, imprimirlo, '
            'recorrerlo paso a paso, abrir todas las variantes de reglas y hacerle al '
            'Rulesbot todas las preguntas que quieras sobre ese juego. Queda asociado a tu '
            'cuenta: que termine una suscripción no te lo quita.'
        ),
    },
    'membership.unlock.where': {
        'en': (
            'You add it from a game, not from this page: open any edition, go to its Info '
            'tab and look for the bookmark-and-star. Your first 3 are free; after that '
            'each edition is US$1.'
        ),
        'zh': (
            '新增的地方在遊戲頁、不在這一頁：打開任一版本，切到「遊戲資訊」分頁，'
            '找那個「書籤中間一顆星」的標記。前 3 款免費，之後每款 US$1。'
        ),
        'ja': (
            '追加はこのページからではなく、ゲーム側から行います。任意のエディションを'
            '開いて「ゲーム情報」タブに進み、「しおりの中央に星」のマークを探して'
            'ください。最初の 3 つは無料、それ以降は 1 つ US$1 です。'
        ),
        'de': (
            'Hinzugefügt wird er beim Spiel, nicht auf dieser Seite: Öffne eine beliebige '
            'Ausgabe, geh auf den Info-Tab und halte nach dem Lesezeichen mit Stern '
            'Ausschau. Die ersten 3 sind kostenlos, danach kostet jede Ausgabe 1 US$.'
        ),
        'fr': (
            "L'ajout se fait depuis un jeu, pas depuis cette page : ouvrez une édition, "
            "allez dans son onglet Infos et cherchez le marque-page avec une étoile. Les "
            "3 premiers sont gratuits, ensuite chaque édition coûte 1 US$."
        ),
        'es': (
            'Se añade desde un juego, no desde esta página: abre cualquier edición, ve a '
            'su pestaña de Información y busca el marcador con una estrella. Los 3 '
            'primeros son gratis; después, cada edición cuesta 1 US$.'
        ),
    },
    'membership.unlock.empty': {
        'en': 'Nothing here yet. Open any game, go to its Info tab and look for the bookmark-and-star.',
        'zh': '這裡還是空的。打開任一款遊戲，切到「遊戲資訊」分頁，找那個「書籤中間一顆星」的標記。',
        'ja': 'まだ何もありません。好きなゲームを開いて「ゲーム情報」タブの「しおりの中央に星」のマークを探してください。',
        'de': 'Hier ist noch nichts. Öffne ein beliebiges Spiel, geh auf den Info-Tab und halte nach dem Lesezeichen mit Stern Ausschau.',
        'fr': "Rien ici pour l'instant. Ouvrez un jeu, allez dans son onglet Infos et cherchez le marque-page avec une étoile.",
        'es': 'Aquí todavía no hay nada. Abre cualquier juego, ve a su pestaña de Información y busca el marcador con una estrella.',
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
    """只刪掉這支新增的 key。改寫過值的舊 key 留著——倒回去也拿不回舊文字，
    刪掉反而會讓頁面直接顯示 key 本身。"""
    Translation = apps.get_model('translation', 'Translation')
    new_keys = [
        'game.unlock.confirm.no_flowchart',
        'game.unlock.pick.no_flowchart_hint',
        'membership.unlock.intro',
        'membership.unlock.where',
    ]
    Translation.objects.filter(key__in=new_keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0034_edition_unlock_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
