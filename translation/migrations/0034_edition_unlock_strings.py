"""Per-edition 永久解鎖的介面字串（免費 3 款 + US$1 加購）。

見 member.EditionUnlock：每位註冊會員可免費自選 3 款 Edition 永久解鎖，用完
之後每款 US$1 加購。解鎖內容是該 edition 流程圖的全螢幕／列印／步驟導覽、
所有非入門 ruleset，以及該 edition 的 Rulesbot 無限查問（不含 GM 講稿）。

文案要講清楚三件事，否則客訴會很多：
  1. 選定後不可變更（唯一例外是該版本還沒有任何已發布流程圖）
  2. 是永久的，訂閱過期也不會收回
  3. 只適用於選定的那一款 edition

'game.unlock.remaining' 後面接的數字由模板拼（{% t %} 不支援插值），所以這句
結尾刻意留成「還可選」「Free picks left」這種可以直接接數字的形式。
"""

from django.db import migrations

STRINGS = {
    # ── 圖示與圖例 ────────────────────────────────────────────────────
    'game.unlock.star': {
        'en': 'Unlocked forever',
        'zh': '已永久解鎖',
        'ja': '永久アンロック済み',
        'de': 'Dauerhaft freigeschaltet',
        'fr': 'Débloqué pour toujours',
        'es': 'Desbloqueado para siempre',
    },
    'game.unlock.star.def': {
        'en': (
            'This edition is one of your permanently unlocked games. You get full-screen '
            'viewing, printing and the step-by-step tour for its flowchart, every ruleset '
            'variant, and unlimited Rulesbot questions about it. It stays yours even if a '
            'subscription later lapses.'
        ),
        'zh': (
            '這個版本是你永久解鎖的遊戲之一。你可以使用它流程圖的全螢幕瀏覽、列印與'
            '逐步導覽，看到所有 ruleset 變體，並無限次向 Rulesbot 詢問這款遊戲。'
            '即使日後會籍到期，這些權限仍然保留。'
        ),
        'ja': (
            'このエディションはあなたが永久にアンロックしたゲームのひとつです。フロー'
            'チャートの全画面表示・印刷・ステップ導線が使え、すべてのルールセットを'
            '閲覧でき、このゲームについて Rulesbot に無制限に質問できます。のちに'
            'サブスクリプションが失効しても、この権限は残ります。'
        ),
        'de': (
            'Diese Ausgabe gehört zu deinen dauerhaft freigeschalteten Spielen. Du kannst '
            'ihren Ablaufplan im Vollbild ansehen, ausdrucken und Schritt für Schritt '
            'durchgehen, siehst alle Regelvarianten und kannst dem Rulesbot unbegrenzt '
            'Fragen dazu stellen. Das bleibt dir erhalten, auch wenn ein Abo später endet.'
        ),
        'fr': (
            "Cette édition fait partie de vos jeux débloqués définitivement. Vous disposez "
            "de l'affichage plein écran, de l'impression et du parcours pas à pas de son "
            "organigramme, de toutes les variantes de règles, et de questions illimitées au "
            "Rulesbot à son sujet. Cela reste acquis même si un abonnement expire ensuite."
        ),
        'es': (
            'Esta edición es uno de tus juegos desbloqueados de forma permanente. Tienes '
            'vista a pantalla completa, impresión y recorrido paso a paso de su diagrama, '
            'todas las variantes de reglas y preguntas ilimitadas al Rulesbot sobre él. '
            'Lo conservas aunque más adelante caduque una suscripción.'
        ),
    },

    # ── 解鎖內容摘要（各狀態共用的說明句）──────────────────────────────
    'game.unlock.perks': {
        'en': (
            'Unlocking this edition gives you full-screen viewing, printing and the '
            'step-by-step tour of its flowchart, every ruleset variant, and unlimited '
            'Rulesbot questions about this game — permanently, for this edition only.'
        ),
        'zh': (
            '解鎖這個版本後，你可以使用它流程圖的全螢幕瀏覽、列印與逐步導覽，看到所有 '
            'ruleset 變體，並無限次向 Rulesbot 詢問這款遊戲——永久有效，但僅限這一個版本。'
        ),
        'ja': (
            'このエディションをアンロックすると、フローチャートの全画面表示・印刷・'
            'ステップ導線が使え、すべてのルールセットを閲覧でき、このゲームについて '
            'Rulesbot に無制限に質問できます。永久に有効ですが、対象はこのエディション'
            'だけです。'
        ),
        'de': (
            'Mit der Freischaltung dieser Ausgabe kannst du ihren Ablaufplan im Vollbild '
            'ansehen, ausdrucken und Schritt für Schritt durchgehen, siehst alle '
            'Regelvarianten und kannst dem Rulesbot unbegrenzt Fragen zu diesem Spiel '
            'stellen — dauerhaft, aber nur für diese Ausgabe.'
        ),
        'fr': (
            "Débloquer cette édition vous donne l'affichage plein écran, l'impression et le "
            "parcours pas à pas de son organigramme, toutes les variantes de règles et des "
            "questions illimitées au Rulesbot sur ce jeu — de façon permanente, mais pour "
            "cette édition uniquement."
        ),
        'es': (
            'Desbloquear esta edición te da vista a pantalla completa, impresión y recorrido '
            'paso a paso de su diagrama, todas las variantes de reglas y preguntas ilimitadas '
            'al Rulesbot sobre este juego: de forma permanente, pero solo para esta edición.'
        ),
    },

    # ── 未登入 ────────────────────────────────────────────────────────
    'game.unlock.login': {
        'en': 'Sign in to pick 3 games to unlock forever, free.',
        'zh': '登入即可免費挑選 3 款遊戲永久解鎖。',
        'ja': 'ログインすると、3 つのゲームを無料で永久にアンロックできます。',
        'de': 'Melde dich an und schalte 3 Spiele kostenlos dauerhaft frei.',
        'fr': 'Connectez-vous pour débloquer gratuitement 3 jeux pour toujours.',
        'es': 'Inicia sesión para desbloquear gratis 3 juegos para siempre.',
    },

    # ── 可用免費名額 ──────────────────────────────────────────────────
    'game.unlock.pick.offer': {
        'en': 'Unlock this edition forever, free',
        'zh': '免費永久解鎖這個版本',
        'ja': 'このエディションを無料で永久にアンロック',
        'de': 'Diese Ausgabe kostenlos dauerhaft freischalten',
        'fr': 'Débloquez cette édition gratuitement, pour toujours',
        'es': 'Desbloquea esta edición gratis, para siempre',
    },
    'game.unlock.pick': {
        'en': 'Use a free pick',
        'zh': '使用免費名額',
        'ja': '無料枠を使う',
        'de': 'Freie Auswahl nutzen',
        'fr': 'Utiliser un choix gratuit',
        'es': 'Usar una selección gratuita',
    },
    'game.unlock.remaining': {
        'en': 'Free picks used:',
        'zh': '已用免費名額：',
        'ja': '使用済みの無料枠：',
        'de': 'Genutzte freie Auswahlen:',
        'fr': 'Choix gratuits utilisés :',
        'es': 'Selecciones gratuitas usadas:',
    },
    'game.unlock.confirm': {
        'en': (
            'Unlock this edition with one of your free picks?\n\n'
            'This cannot be changed later. The only exception is while this edition still '
            'has no published flowchart at all — until then you can give the pick back.'
        ),
        'zh': (
            '要用一個免費名額解鎖這個版本嗎？\n\n'
            '選定後無法變更。唯一的例外是這個版本目前還沒有任何已發布的流程圖——'
            '在那之前你可以把名額退回。'
        ),
        'ja': (
            '無料枠を 1 つ使ってこのエディションをアンロックしますか？\n\n'
            'あとから変更はできません。唯一の例外は、このエディションにまだ公開済みの'
            'フローチャートが 1 つもない間だけで、そのあいだは枠を戻せます。'
        ),
        'de': (
            'Diese Ausgabe mit einer deiner freien Auswahlen freischalten?\n\n'
            'Das lässt sich später nicht mehr ändern. Einzige Ausnahme: Solange es zu dieser '
            'Ausgabe noch gar keinen veröffentlichten Ablaufplan gibt, kannst du die Auswahl '
            'zurückgeben.'
        ),
        'fr': (
            "Débloquer cette édition avec l'un de vos choix gratuits ?\n\n"
            "Ce choix ne pourra plus être modifié. Seule exception : tant que cette édition "
            "n'a encore aucun organigramme publié, vous pouvez récupérer votre choix."
        ),
        'es': (
            '¿Desbloquear esta edición con una de tus selecciones gratuitas?\n\n'
            'No podrá cambiarse después. La única excepción es mientras esta edición todavía '
            'no tenga ningún diagrama publicado: hasta entonces puedes recuperar la selección.'
        ),
    },

    # ── 已解鎖 ────────────────────────────────────────────────────────
    'game.unlock.picked': {
        'en': 'Unlocked forever',
        'zh': '已永久解鎖',
        'ja': '永久アンロック済み',
        'de': 'Dauerhaft freigeschaltet',
        'fr': 'Débloqué pour toujours',
        'es': 'Desbloqueado para siempre',
    },
    'game.unlock.success': {
        'en': 'Unlocked. This edition is yours for good.',
        'zh': '已解鎖。這個版本永久屬於你。',
        'ja': 'アンロックしました。このエディションはずっとあなたのものです。',
        'de': 'Freigeschaltet. Diese Ausgabe bleibt dauerhaft deine.',
        'fr': 'Débloqué. Cette édition est à vous pour de bon.',
        'es': 'Desbloqueada. Esta edición es tuya para siempre.',
    },

    # ── 退回名額 ──────────────────────────────────────────────────────
    'game.unlock.release.hint': {
        'en': (
            'This edition has no published flowchart yet, so your pick is not locked in. '
            'You can take it back and use it on another game.'
        ),
        'zh': (
            '這個版本還沒有已發布的流程圖，所以你的選擇尚未定案，可以退回名額改選'
            '其他遊戲。'
        ),
        'ja': (
            'このエディションにはまだ公開済みのフローチャートがないため、選択は確定して'
            'いません。枠を戻して別のゲームに使えます。'
        ),
        'de': (
            'Zu dieser Ausgabe gibt es noch keinen veröffentlichten Ablaufplan, deine Auswahl '
            'ist also noch nicht endgültig. Du kannst sie zurücknehmen und für ein anderes '
            'Spiel verwenden.'
        ),
        'fr': (
            "Cette édition n'a pas encore d'organigramme publié : votre choix n'est donc pas "
            "définitif. Vous pouvez le récupérer et l'utiliser sur un autre jeu."
        ),
        'es': (
            'Esta edición aún no tiene ningún diagrama publicado, así que tu selección no es '
            'definitiva. Puedes recuperarla y usarla en otro juego.'
        ),
    },
    'game.unlock.release': {
        'en': 'Take this pick back',
        'zh': '退回這個名額',
        'ja': 'この枠を戻す',
        'de': 'Auswahl zurücknehmen',
        'fr': 'Récupérer ce choix',
        'es': 'Recuperar esta selección',
    },
    'game.unlock.release.confirm': {
        'en': 'Take this free pick back and use it on another game?',
        'zh': '要退回這個免費名額，改用在其他遊戲上嗎？',
        'ja': 'この無料枠を戻して、別のゲームに使いますか？',
        'de': 'Diese freie Auswahl zurücknehmen und für ein anderes Spiel verwenden?',
        'fr': 'Récupérer ce choix gratuit pour l’utiliser sur un autre jeu ?',
        'es': '¿Recuperar esta selección gratuita para usarla en otro juego?',
    },
    'game.unlock.released': {
        'en': 'Pick returned. You can use it on another game.',
        'zh': '名額已退回，可以改用在其他遊戲上。',
        'ja': '枠を戻しました。別のゲームに使えます。',
        'de': 'Auswahl zurückgegeben. Du kannst sie für ein anderes Spiel nutzen.',
        'fr': 'Choix récupéré. Vous pouvez l’utiliser sur un autre jeu.',
        'es': 'Selección recuperada. Puedes usarla en otro juego.',
    },

    # ── US$1 加購 ─────────────────────────────────────────────────────
    'game.unlock.buy.offer': {
        'en': 'Your free picks are used up — unlock this edition for US$1',
        'zh': '免費名額已用完——US$1 即可解鎖這個版本',
        'ja': '無料枠は使い切りました——US$1 でこのエディションをアンロック',
        'de': 'Deine freien Auswahlen sind aufgebraucht — diese Ausgabe für 1 US$ freischalten',
        'fr': 'Vos choix gratuits sont épuisés — débloquez cette édition pour 1 US$',
        'es': 'Se acabaron tus selecciones gratuitas: desbloquea esta edición por 1 US$',
    },
    'game.unlock.buy': {
        'en': 'Unlock forever',
        'zh': '永久解鎖',
        'ja': '永久アンロック',
        'de': 'Dauerhaft freischalten',
        'fr': 'Débloquer pour toujours',
        'es': 'Desbloquear para siempre',
    },
    'game.unlock.buy.confirm': {
        'en': (
            'Unlock this edition forever for US$1?\n\n'
            'You will be taken to Stripe to pay. This is a one-time payment, not a '
            'subscription, and it applies to this edition only. It cannot be changed to a '
            'different game afterwards.'
        ),
        'zh': (
            '要以 US$1 永久解鎖這個版本嗎？\n\n'
            '接下來會前往 Stripe 付款。這是一次性付款、不是訂閱，而且只適用於這一個版本，'
            '付款後無法改成其他遊戲。'
        ),
        'ja': (
            'US$1 でこのエディションを永久にアンロックしますか？\n\n'
            'このあと Stripe の決済画面に移動します。これはサブスクリプションではなく'
            '買い切りで、対象はこのエディションだけです。購入後に別のゲームへ変更する'
            'ことはできません。'
        ),
        'de': (
            'Diese Ausgabe für 1 US$ dauerhaft freischalten?\n\n'
            'Du wirst zur Zahlung zu Stripe weitergeleitet. Es handelt sich um eine einmalige '
            'Zahlung, kein Abo, und sie gilt nur für diese Ausgabe. Ein späterer Wechsel auf '
            'ein anderes Spiel ist nicht möglich.'
        ),
        'fr': (
            "Débloquer cette édition pour toujours pour 1 US$ ?\n\n"
            "Vous allez être redirigé vers Stripe pour le paiement. Il s'agit d'un paiement "
            "unique, pas d'un abonnement, et il ne concerne que cette édition. Il ne pourra "
            "pas être transféré vers un autre jeu."
        ),
        'es': (
            '¿Desbloquear esta edición para siempre por 1 US$?\n\n'
            'Te llevaremos a Stripe para pagar. Es un pago único, no una suscripción, y se '
            'aplica solo a esta edición. Después no podrá cambiarse a otro juego.'
        ),
    },

    # ── 免費名額用完、且這款還沒有流程圖 ──────────────────────────────
    'game.unlock.no_flowchart_yet': {
        'en': 'No flowchart published for this edition yet, so it cannot be unlocked.',
        'zh': '這個版本還沒有已發布的流程圖，因此尚無法解鎖。',
        'ja': 'このエディションにはまだ公開済みのフローチャートがないため、アンロックできません。',
        'de': 'Für diese Ausgabe ist noch kein Ablaufplan veröffentlicht, sie lässt sich daher nicht freischalten.',
        'fr': "Aucun organigramme n'est encore publié pour cette édition : elle ne peut donc pas être débloquée.",
        'es': 'Aún no hay ningún diagrama publicado para esta edición, así que no se puede desbloquear.',
    },

    # ── 錯誤訊息 ──────────────────────────────────────────────────────
    'game.unlock.error.quota': {
        'en': 'Your free picks are used up. You can unlock more editions for US$1 each.',
        'zh': '免費名額已用完。你可以每款 US$1 加購其他版本。',
        'ja': '無料枠を使い切りました。ほかのエディションは 1 つ US$1 でアンロックできます。',
        'de': 'Deine freien Auswahlen sind aufgebraucht. Weitere Ausgaben kannst du für je 1 US$ freischalten.',
        'fr': 'Vos choix gratuits sont épuisés. Vous pouvez débloquer d’autres éditions pour 1 US$ chacune.',
        'es': 'Se acabaron tus selecciones gratuitas. Puedes desbloquear otras ediciones por 1 US$ cada una.',
    },
    'game.unlock.error.locked_in': {
        'en': 'This pick is final and cannot be changed.',
        'zh': '這個選擇已定案，無法變更。',
        'ja': 'この選択は確定済みで、変更できません。',
        'de': 'Diese Auswahl ist endgültig und kann nicht geändert werden.',
        'fr': 'Ce choix est définitif et ne peut pas être modifié.',
        'es': 'Esta selección es definitiva y no se puede cambiar.',
    },
    'game.unlock.error.no_flowchart': {
        'en': 'This edition has no published flowchart yet, so it cannot be purchased.',
        'zh': '這個版本還沒有已發布的流程圖，因此無法購買。',
        'ja': 'このエディションにはまだ公開済みのフローチャートがないため、購入できません。',
        'de': 'Für diese Ausgabe ist noch kein Ablaufplan veröffentlicht, sie kann daher nicht gekauft werden.',
        'fr': "Cette édition n'a pas encore d'organigramme publié : elle ne peut pas être achetée.",
        'es': 'Esta edición aún no tiene ningún diagrama publicado, así que no se puede comprar.',
    },
    'game.unlock.error.generic': {
        'en': 'Something went wrong. Please try again.',
        'zh': '發生錯誤，請稍後再試。',
        'ja': 'エラーが発生しました。もう一度お試しください。',
        'de': 'Etwas ist schiefgelaufen. Bitte versuche es erneut.',
        'fr': 'Une erreur est survenue. Veuillez réessayer.',
        'es': 'Algo salió mal. Vuelve a intentarlo.',
    },

    # ── 會員頁的清單 ──────────────────────────────────────────────────
    'membership.unlock.heading': {
        'en': 'My permanently unlocked editions',
        'zh': '我的永久解鎖版本',
        'ja': '永久アンロック済みのエディション',
        'de': 'Meine dauerhaft freigeschalteten Ausgaben',
        'fr': 'Mes éditions débloquées définitivement',
        'es': 'Mis ediciones desbloqueadas permanentemente',
    },
    'membership.unlock.empty': {
        'en': 'You have not unlocked any editions yet. Open any game and look for the star.',
        'zh': '你還沒有解鎖任何版本。打開任一款遊戲，找找那顆星星。',
        'ja': 'まだアンロックしたエディションはありません。好きなゲームを開いて星のマークを探してください。',
        'de': 'Du hast noch keine Ausgaben freigeschaltet. Öffne ein beliebiges Spiel und halte nach dem Stern Ausschau.',
        'fr': "Vous n'avez encore débloqué aucune édition. Ouvrez un jeu et cherchez l'étoile.",
        'es': 'Todavía no has desbloqueado ninguna edición. Abre cualquier juego y busca la estrella.',
    },
    'game.unlock.source.free': {
        'en': '(free pick)',
        'zh': '（免費名額）',
        'ja': '（無料枠）',
        'de': '(freie Auswahl)',
        'fr': '(choix gratuit)',
        'es': '(selección gratuita)',
    },
    'game.unlock.source.paid': {
        'en': '(purchased)',
        'zh': '（已購買）',
        'ja': '（購入済み）',
        'de': '(gekauft)',
        'fr': '(acheté)',
        'es': '(comprado)',
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
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key__in=STRINGS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0033_alter_translation_value'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
