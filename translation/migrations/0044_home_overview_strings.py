"""首頁 hero 下方「Overview」橫幅與「More ways to learn」三張卡的字串。"""

from django.db import migrations

STRINGS = {
    'home.overview.eyebrow': {
        'en': 'Visual. Clear. Complete.',
        'zh': '視覺化、清楚、完整',
        'ja': 'ビジュアルで、わかりやすく、漏れなく',
        'de': 'Visuell. Klar. Vollständig.',
        'fr': 'Visuel. Clair. Complet.',
        'es': 'Visual. Claro. Completo.',
    },
    'home.overview.title': {
        'en': 'Understand the whole game at a glance',
        'zh': '一眼看懂整場遊戲',
        'ja': 'ゲーム全体をひと目で理解',
        'de': 'Das ganze Spiel auf einen Blick verstehen',
        'fr': 'Comprenez tout le jeu en un coup d’œil',
        'es': 'Entiende todo el juego de un vistazo',
    },
    'home.overview.desc': {
        'en': 'From setup to victory, follow the game visually. Our flowcharts turn complex rulebooks into simple, step-by-step guides.',
        'zh': '從準備到獲勝，用圖像跟著遊戲走。我們的流程圖把複雜的規則書變成簡單的逐步指引。',
        'ja': '準備から勝利まで、ゲームの流れを視覚的に追えます。複雑なルールブックを、シンプルなステップ式ガイドに。',
        'de': 'Von der Vorbereitung bis zum Sieg: Verfolge das Spiel visuell. Unsere Flussdiagramme machen komplexe Regelhefte zu einfachen Schritt-für-Schritt-Anleitungen.',
        'fr': 'De la mise en place à la victoire, suivez le jeu visuellement. Nos organigrammes transforment des règles complexes en guides simples, étape par étape.',
        'es': 'Desde la preparación hasta la victoria, sigue el juego de forma visual. Nuestros diagramas convierten reglamentos complejos en guías sencillas paso a paso.',
    },
    'home.overview.note': {
        'en': 'From setup to victory.',
        'zh': '從準備到獲勝。',
        'ja': '準備から勝利まで。',
        'de': 'Von der Vorbereitung zum Sieg.',
        'fr': 'De la mise en place à la victoire.',
        'es': 'De la preparación a la victoria.',
    },
    'home.learn.title': {
        'en': 'More ways to learn',
        'zh': '更多學習方式',
        'ja': 'そのほかの学び方',
        'de': 'Weitere Wege zum Lernen',
        'fr': 'Autres façons d’apprendre',
        'es': 'Más formas de aprender',
    },
    'home.learn.rulesbot_title': {
        'en': 'Ask the Rulesbot',
        'zh': '問問規則機器人',
        'ja': 'ルールボットに聞く',
        'de': 'Frag den Regelbot',
        'fr': 'Demandez au Rulesbot',
        'es': 'Pregunta al Rulesbot',
    },
    'home.learn.rulesbot_desc': {
        'en': 'Get clear answers without digging through the rulebook. Ask a rule question and get a plain-language answer with sources.',
        'zh': '不用翻規則書也能得到清楚的答案。提出規則問題，就能得到附出處的白話回答。',
        'ja': 'ルールブックをめくらなくても、はっきりした答えが得られます。ルールの質問に、出典つきのやさしい言葉で回答します。',
        'de': 'Klare Antworten, ohne im Regelheft zu blättern. Stelle eine Regelfrage und erhalte eine verständliche Antwort mit Quellen.',
        'fr': 'Obtenez des réponses claires sans fouiller le livret. Posez une question de règle et recevez une réponse simple, avec ses sources.',
        'es': 'Obtén respuestas claras sin buscar en el reglamento. Haz una pregunta de reglas y recibe una respuesta sencilla con fuentes.',
    },
    'home.learn.script_title': {
        'en': 'Teach with a Guide Script',
        'zh': '用教學講稿帶人玩',
        'ja': '説明スクリプトで教える',
        'de': 'Erklären mit einem Erklärskript',
        'fr': 'Expliquer avec un script',
        'es': 'Enseña con un guion',
    },
    'home.learn.script_desc': {
        'en': 'Explain the game in a natural sequence. Ready-to-use teaching scripts help you get everyone to the table faster.',
        'zh': '依自然的順序講解遊戲。現成的教學講稿讓大家更快上桌開玩。',
        'ja': '自然な順序でゲームを説明。すぐ使える説明スクリプトで、みんなをすばやくテーブルへ。',
        'de': 'Erkläre das Spiel in natürlicher Reihenfolge. Sofort einsetzbare Skripte bringen alle schneller an den Tisch.',
        'fr': 'Expliquez le jeu dans un ordre naturel. Des scripts prêts à l’emploi mettent tout le monde à table plus vite.',
        'es': 'Explica el juego en un orden natural. Guiones listos para usar sientan a todos a la mesa más rápido.',
    },
    'home.learn.competency_title': {
        'en': 'Explore Competencies',
        'zh': '探索能力指標',
        'ja': 'コンピテンシーを知る',
        'de': 'Kompetenzen entdecken',
        'fr': 'Explorer les compétences',
        'es': 'Explora las competencias',
    },
    'home.learn.competency_desc': {
        'en': 'See what skills a game draws on. Discover the thinking, social and personal skills behind your favorite games.',
        'zh': '看看遊戲會用到哪些能力，了解你最愛的遊戲背後的思考、社交與個人技能。',
        'ja': 'ゲームがどんな力を使うかをチェック。お気に入りのゲームの裏にある思考力・社会性・個人のスキルがわかります。',
        'de': 'Sieh, welche Fähigkeiten ein Spiel fordert. Entdecke die Denk-, Sozial- und persönlichen Kompetenzen hinter deinen Lieblingsspielen.',
        'fr': 'Découvrez les compétences mobilisées par un jeu : réflexion, aptitudes sociales et personnelles derrière vos jeux préférés.',
        'es': 'Descubre qué habilidades usa un juego: el pensamiento, lo social y lo personal detrás de tus juegos favoritos.',
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
        ('translation', '0043_home_guides_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
