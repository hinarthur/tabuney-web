"""GM 講稿付費牆的通用預覽文字（3 個標題 + 3 段內文）。

原本未達訂閱等級時，頁面塞的是 _mask_text() 打碼後的真實講稿：視覺上 blur，
原始碼裡是同字集的隨機亂碼。這對 GEO（生成式搜尋引擎）很不友善 —— 爬蟲讀到的
是一整頁沒有語意的亂碼，等於這一頁對 AI 回答引擎完全沒有內容。

改成這六句所有版本共用的通用說明：講稿是什麼、怎麼在牌桌上用、誰讀得到全文。
視覺上仍然 blur（付費內容不外流不變 —— 這裡本來就一個字的真實講稿都沒有），
但爬蟲讀到的是通順的句子。內容刻意不提任何特定遊戲，六種語言各寫一份。
"""

from django.db import migrations

STRINGS = {
    # ── 第一段：講稿裡有什麼 ──────────────────────────────────────────
    'game.script.teaser.h1': {
        'en': 'What this host script contains',
        'zh': '這份主持人講稿包含什麼',
        'ja': 'このホスト用進行台本に書かれていること',
        'de': 'Was in diesem Moderationsskript steht',
        'fr': "Ce que contient ce script d'animation",
        'es': 'Qué contiene este guion de anfitrión',
    },
    'game.script.teaser.p1': {
        'en': (
            'Every host script on Tabuney is written in the first person and takes about '
            'five minutes to read aloud. It follows the same teaching order every time: an '
            'opening that sets the scene, the goal of the game, the setup, how a turn flows, '
            'how the game ends, and a short closing. Components are introduced where they '
            'come up, so nobody has to sit through a separate parts list.'
        ),
        'zh': (
            'Tabuney 的每一份主持人講稿都以第一人稱寫成，朗讀約五分鐘。內容依固定的教學'
            '順序展開：開場營造氣氛、說明遊戲目標、擺設遊戲、回合流程、遊戲如何結束，'
            '最後收尾。配件在用得到的地方自然帶入，不必另外唸一長串配件清單。'
        ),
        'ja': (
            'Tabuney のホスト用進行台本はすべて一人称で書かれ、読み上げると約 5 分です。'
            '導入で場の雰囲気をつくり、ゲームの目的、セットアップ、手番の流れ、終了条件、'
            '締めの言葉という決まった順序で進みます。コンポーネントは必要な場面で自然に'
            '紹介するので、部品リストを延々と読み上げる必要はありません。'
        ),
        'de': (
            'Jedes Moderationsskript auf Tabuney ist in der Ich-Form geschrieben und dauert '
            'vorgelesen etwa fünf Minuten. Es folgt immer derselben Reihenfolge: eine '
            'Eröffnung, die die Stimmung setzt, das Spielziel, der Aufbau, der Ablauf eines '
            'Zuges, das Spielende und ein kurzer Abschluss. Das Material kommt dort zur '
            'Sprache, wo es gebraucht wird — eine separate Materialliste muss sich niemand '
            'anhören.'
        ),
        'fr': (
            "Chaque script d'animation de Tabuney est écrit à la première personne et se lit "
            "à voix haute en cinq minutes environ. Il suit toujours le même ordre : une "
            "ouverture qui plante le décor, le but du jeu, la mise en place, le déroulement "
            "d'un tour, la fin de la partie et une courte conclusion. Le matériel est "
            "présenté au fil du texte, sans liste de composants à réciter."
        ),
        'es': (
            'Todos los guiones de anfitrión de Tabuney están escritos en primera persona y se '
            'leen en voz alta en unos cinco minutos. Siguen siempre el mismo orden: una '
            'apertura que crea ambiente, el objetivo del juego, la preparación, cómo '
            'transcurre un turno, cómo termina la partida y un breve cierre. Los componentes '
            'se presentan cuando hacen falta, sin recitar una lista de materiales aparte.'
        ),
    },

    # ── 第二段：怎麼用 ────────────────────────────────────────────────
    'game.script.teaser.h2': {
        'en': 'How to use it at the table',
        'zh': '怎麼在牌桌上使用',
        'ja': '卓での使い方',
        'de': 'So nutzt du es am Spieltisch',
        'fr': "Comment l'utiliser à la table",
        'es': 'Cómo usarlo en la mesa',
    },
    'game.script.teaser.p2': {
        'en': (
            'Read it out loud before the first turn. The script speaks as a host in character, '
            'so new players hear what the game is about before they hear a single rule — no '
            'reciting the rulebook, no starting the explanation over halfway through the first '
            'round. You can stop after any section to deal out components or answer a '
            'question, then pick up where you left off.'
        ),
        'zh': (
            '在第一個回合開始前朗讀出來。講稿以主持人的角色口吻說話，新手會先聽懂這款'
            '遊戲在玩什麼，才聽到第一條規則——不必照著規則書唸，也不會玩到一半還要重講'
            '一次。你可以在任何一段之後停下來發配件或回答問題，再接著往下唸。'
        ),
        'ja': (
            '最初の手番が始まる前に、そのまま読み上げてください。台本はホストが役になり'
            'きって語る形なので、初めての人もルールを聞く前にこのゲームがどんな遊びなのか'
            'をつかめます。ルールブックを棒読みする必要も、1 ラウンド目の途中で説明し直す'
            '必要もありません。どの段落の後でも一度止めてコンポーネントを配ったり質問に'
            '答えたりしてから、続きを読み進められます。'
        ),
        'de': (
            'Lies es vor dem ersten Zug laut vor. Das Skript spricht in der Rolle der '
            'Spielleitung, damit Neulinge erst verstehen, worum es im Spiel geht, bevor sie '
            'die erste Regel hören — kein Vorlesen aus dem Regelheft, kein Neuerklären mitten '
            'in der ersten Runde. Nach jedem Abschnitt kannst du anhalten, Material austeilen '
            'oder Fragen beantworten und dann weiterlesen.'
        ),
        'fr': (
            "Lisez-le à voix haute avant le premier tour. Le script parle dans la peau de "
            "l'animateur : les nouveaux joueurs comprennent de quoi parle le jeu avant "
            "d'entendre la première règle — pas de lecture du livret, pas d'explication à "
            "reprendre au milieu de la première manche. Vous pouvez vous arrêter après "
            "n'importe quelle section pour distribuer du matériel ou répondre à une question, "
            "puis reprendre où vous en étiez."
        ),
        'es': (
            'Léelo en voz alta antes del primer turno. El guion habla desde el papel del '
            'anfitrión, así que quienes juegan por primera vez entienden de qué va el juego '
            'antes de oír la primera regla: sin leer el reglamento y sin tener que volver a '
            'explicarlo a mitad de la primera ronda. Puedes parar al final de cualquier '
            'sección para repartir componentes o responder una pregunta, y luego seguir donde '
            'lo dejaste.'
        ),
    },

    # ── 第三段：誰讀得到全文 ──────────────────────────────────────────
    'game.script.teaser.h3': {
        'en': 'Who can read the full script',
        'zh': '誰能讀到完整講稿',
        'ja': '全文を読めるのは誰か',
        'de': 'Wer das vollständige Skript lesen kann',
        'fr': 'Qui peut lire le script complet',
        'es': 'Quién puede leer el guion completo',
    },
    'game.script.teaser.p3': {
        'en': (
            'The full text of each script is written for one specific edition and is available '
            'to Tabuney members. Upgrade your membership to unlock the complete host script '
            'for this game, along with the host persona, the player persona, and the '
            'atmosphere the script is written to create.'
        ),
        'zh': (
            '每一份講稿都是為特定版本量身撰寫，完整內容開放給 Tabuney 會員閱讀。升級會籍'
            '即可解鎖這款遊戲的完整主持人講稿，以及主持人角色設定、玩家角色設定，還有講稿'
            '要營造的氛圍。'
        ),
        'ja': (
            '各台本は特定のエディションのために書き下ろされており、全文は Tabuney の'
            'メンバーが読めます。メンバーシップをアップグレードすると、このゲームの完全な'
            'ホスト台本に加えて、ホストのペルソナ、プレイヤーのペルソナ、台本がつくり出す'
            '雰囲気の設定も読めるようになります。'
        ),
        'de': (
            'Der vollständige Text ist für genau diese Ausgabe geschrieben und steht '
            'Tabuney-Mitgliedern offen. Mit einem Upgrade deiner Mitgliedschaft schaltest du '
            'das komplette Moderationsskript zu diesem Spiel frei — samt Rolle der '
            'Spielleitung, Rolle der Mitspielenden und der Stimmung, die das Skript erzeugen '
            'soll.'
        ),
        'fr': (
            "Le texte intégral est écrit pour cette édition précise et il est réservé aux "
            "membres de Tabuney. Passez à un abonnement supérieur pour débloquer le script "
            "d'animation complet de ce jeu, ainsi que le rôle de l'animateur, celui des "
            "joueurs et l'ambiance que le script cherche à créer."
        ),
        'es': (
            'El texto completo está escrito para esta edición concreta y está disponible para '
            'los miembros de Tabuney. Mejora tu membresía para desbloquear el guion de '
            'anfitrión completo de este juego, junto con el personaje del anfitrión, el de '
            'los jugadores y la atmósfera que el guion busca crear.'
        ),
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
        ('translation', '0031_edition_tab_seo_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
