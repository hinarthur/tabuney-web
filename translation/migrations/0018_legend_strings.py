"""
edition_detail 的 ℹ️ 從「僅解說 PLATVM 技能」擴大為整個 info-card 的圖示說明，
分成 Collection Status / Preference / Stats / Competency 四個分頁。
補上分頁標題與各圖示的詳細解說翻譯字串。
"""

from django.db import migrations

STRINGS = {
    'game.info.legend': {
        'en': 'Icon Legend',
        'zh': '圖示說明',
        'ja': 'アイコンの説明',
        'de': 'Symbolerklärung',
        'fr': 'Légende des icônes',
        'es': 'Leyenda de iconos',
    },
    'game.legend.title': {
        'en': 'Icon Legend',
        'zh': '圖示說明',
        'ja': 'アイコンの説明',
        'de': 'Symbolerklärung',
        'fr': 'Légende des icônes',
        'es': 'Leyenda de iconos',
    },
    'game.legend.tab.status': {
        'en': 'Collection',
        'zh': '收藏狀態',
        'ja': 'コレクション',
        'de': 'Sammlung',
        'fr': 'Collection',
        'es': 'Colección',
    },
    'game.legend.tab.preference': {
        'en': 'Preference',
        'zh': '喜好評分',
        'ja': '好み',
        'de': 'Vorliebe',
        'fr': 'Préférence',
        'es': 'Preferencia',
    },
    'game.legend.tab.stats': {
        'en': 'Stats',
        'zh': '遊戲資訊',
        'ja': '基本情報',
        'de': 'Daten',
        'fr': 'Statistiques',
        'es': 'Datos',
    },
    'game.legend.tab.competency': {
        'en': 'Skills',
        'zh': '能力指標',
        'ja': 'スキル',
        'de': 'Fähigkeiten',
        'fr': 'Compétences',
        'es': 'Habilidades',
    },
    'game.collection.past.def': {
        'en': "You've played this game before but don't currently own it.",
        'zh': '你玩過這款遊戲，但目前不擁有它。',
        'ja': '以前プレイしたことがあるが、現在は所有していないゲームです。',
        'de': 'Du hast dieses Spiel schon einmal gespielt, besitzt es aber derzeit nicht.',
        'fr': "Vous avez déjà joué à ce jeu, mais vous ne le possédez pas actuellement.",
        'es': 'Has jugado este juego antes, pero actualmente no lo tienes.',
    },
    'game.collection.owned.def': {
        'en': 'This game is currently in your collection.',
        'zh': '這款遊戲目前在你的收藏中。',
        'ja': '現在あなたのコレクションにあるゲームです。',
        'de': 'Dieses Spiel befindet sich derzeit in deiner Sammlung.',
        'fr': 'Ce jeu fait actuellement partie de votre collection.',
        'es': 'Este juego está actualmente en tu colección.',
    },
    'game.collection.wish.def': {
        'en': "You'd like to get this game in the future.",
        'zh': '你希望未來能擁有這款遊戲。',
        'ja': '将来手に入れたいと思っているゲームです。',
        'de': 'Dieses Spiel möchtest du dir in Zukunft zulegen.',
        'fr': "Vous aimeriez posséder ce jeu à l'avenir.",
        'es': 'Te gustaría tener este juego en el futuro.',
    },
    'game.preference.nightmare.def': {
        'en': 'You really dislike this game.',
        'zh': '你非常不喜歡這款遊戲。',
        'ja': 'このゲームがとても苦手です。',
        'de': 'Du magst dieses Spiel überhaupt nicht.',
        'fr': "Vous n'aimez vraiment pas ce jeu.",
        'es': 'Realmente no te gusta este juego.',
    },
    'game.preference.nah.def': {
        'en': "This game isn't really for you.",
        'zh': '這款遊戲不太合你的口味。',
        'ja': 'このゲームはあまり好みではありません。',
        'de': 'Dieses Spiel ist nicht wirklich dein Fall.',
        'fr': "Ce jeu n'est pas vraiment pour vous.",
        'es': 'Este juego no es realmente para ti.',
    },
    'game.preference.nice.def': {
        'en': 'You enjoy playing this game.',
        'zh': '你喜歡玩這款遊戲。',
        'ja': 'このゲームを楽しんでいます。',
        'de': 'Du spielst dieses Spiel gerne.',
        'fr': 'Vous aimez jouer à ce jeu.',
        'es': 'Disfrutas jugando este juego.',
    },
    'game.preference.amazing.def': {
        'en': 'This is one of your favorite games.',
        'zh': '這是你最喜愛的遊戲之一。',
        'ja': 'お気に入りのゲームの一つです。',
        'de': 'Das ist eines deiner Lieblingsspiele.',
        'fr': "C'est l'un de vos jeux préférés.",
        'es': 'Este es uno de tus juegos favoritos.',
    },
    'game.label.players.def': {
        'en': 'The number of players this game supports.',
        'zh': '這款遊戲支援的遊玩人數。',
        'ja': 'このゲームに対応するプレイヤー人数です。',
        'de': 'Die Anzahl der Spieler, die dieses Spiel unterstützt.',
        'fr': 'Le nombre de joueurs pris en charge par ce jeu.',
        'es': 'El número de jugadores que admite este juego.',
    },
    'game.label.playtime.def': {
        'en': 'How long a typical game session takes, in minutes.',
        'zh': '一場遊戲大約需要的時間（分鐘）。',
        'ja': '1ゲームにかかる目安の時間（分）です。',
        'de': 'Wie lange eine typische Spielsitzung dauert, in Minuten.',
        'fr': "Durée approximative d'une partie type, en minutes.",
        'es': 'Cuánto dura normalmente una partida, en minutos.',
    },
    'game.label.age.def': {
        'en': 'The minimum recommended age for players.',
        'zh': '建議的最低遊玩年齡。',
        'ja': '推奨される最低プレイ年齢です。',
        'de': 'Das empfohlene Mindestalter für Spieler.',
        'fr': 'L\'âge minimum recommandé pour les joueurs.',
        'es': 'La edad mínima recomendada para los jugadores.',
    },
    'game.label.reading_density.def': {
        'en': "How much reading is involved in the game's components (not counting cue cards or the rulebook).",
        'zh': '遊戲配件中需要閱讀的文字量（不含提示卡或規則書）。',
        'ja': 'ゲームコンポーネントに含まれる読解量です（ヒントカードやルールブックは含みません）。',
        'de': 'Wie viel Lesen die Spielkomponenten erfordern (ohne Hinweiskarten oder Regelheft).',
        'fr': 'La quantité de lecture nécessaire dans les composants du jeu (hors cartes indices ou règles).',
        'es': 'Cuánta lectura implican los componentes del juego (sin contar las tarjetas de pistas ni el reglamento).',
    },
    'game.reading_density.none.def': {
        'en': 'No text — components rely on symbols, colors, or shapes only.',
        'zh': '完全無文字，僅靠符號、顏色或形狀辨識。',
        'ja': '文字はなく、記号・色・形だけで判別します。',
        'de': 'Kein Text — die Komponenten basieren nur auf Symbolen, Farben oder Formen.',
        'fr': 'Aucun texte — les composants reposent uniquement sur des symboles, couleurs ou formes.',
        'es': 'Sin texto: los componentes se basan solo en símbolos, colores o formas.',
    },
    'game.reading_density.labels.def': {
        'en': 'Short words or labels only, like names or single terms.',
        'zh': '僅有簡短的單字或標籤，例如名稱或單一詞彙。',
        'ja': '名前や単語など、短いラベルのみです。',
        'de': 'Nur kurze Wörter oder Beschriftungen, wie Namen oder einzelne Begriffe.',
        'fr': 'Seulement des mots ou étiquettes courts, comme des noms ou termes isolés.',
        'es': 'Solo palabras o etiquetas cortas, como nombres o términos sueltos.',
    },
    'game.reading_density.simple.def': {
        'en': 'Short, simple sentences that are quick to read during play.',
        'zh': '簡短、簡單的句子，遊玩時能快速閱讀。',
        'ja': 'プレイ中にすぐ読める、短く簡単な文章です。',
        'de': 'Kurze, einfache Sätze, die sich beim Spielen schnell lesen lassen.',
        'fr': 'Des phrases courtes et simples, faciles à lire pendant la partie.',
        'es': 'Frases cortas y sencillas que se leen rápido durante la partida.',
    },
    'game.reading_density.complex.def': {
        'en': 'Longer passages or dense text that require more reading time.',
        'zh': '較長段落或密集文字，需要較多閱讀時間。',
        'ja': '長めの文章や情報量の多いテキストで、読むのに時間がかかります。',
        'de': 'Längere Passagen oder dichter Text, der mehr Lesezeit erfordert.',
        'fr': 'Des passages plus longs ou un texte dense qui demandent plus de temps de lecture.',
        'es': 'Pasajes más largos o texto denso que requieren más tiempo de lectura.',
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
    Translation.objects.filter(key__in=list(STRINGS.keys())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0017_reading_density_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
