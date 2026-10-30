"""
index.html、membership.html、interaction/collection.html、about.html 先前都沒有
自己的 meta description，跟其他頁面共用 seo.default.description，構成
Search Console 會標記的「重複 meta description」。這裡補上各自專屬的文案。
"""

from django.db import migrations

STRINGS = {
    'seo.index.description': {
        'en': 'Tabuney is your board game hub: ask the AI Rulesbot any rules question '
              'and get instant answers, browse the latest board game news and reviews.',
        'zh': 'Tabuney 是你的桌遊入口網站：用 AI 規則問答機器人即問即答任何規則疑問，還能瀏覽最新桌遊新聞與評測。',
        'ja': 'Tabuneyはボードゲームのハブサイト。AIルールボットに質問すればルールを即座に回答、'
              '最新のボードゲームニュースやレビューも閲覧できます。',
        'de': 'Tabuney ist dein Brettspiel-Portal: Stelle dem KI-Regelbot jede Regelfrage '
              'und erhalte sofort Antworten, entdecke die neuesten Brettspiel-News und Rezensionen.',
        'fr': "Tabuney est votre portail de jeux de société : posez n'importe quelle question de règles "
              "à l'IA Rulesbot et obtenez une réponse instantanée, découvrez les dernières actualités et critiques.",
        'es': 'Tabuney es tu portal de juegos de mesa: pregunta cualquier duda de reglas al Rulesbot de IA '
              'y obtén respuestas al instante, explora las últimas noticias y reseñas de juegos de mesa.',
    },
    'seo.membership.description': {
        'en': "Compare Tabuney's Free, Member and Subscriber plans — chatbot query limits, "
              'flowchart access, translations, printing and GM scripts.',
        'zh': '比較 Tabuney 免費、會員、訂閱方案：聊天機器人問答額度、流程圖、翻譯、列印與 GM 講稿等權益。',
        'ja': 'Tabuneyの無料・メンバー・サブスクリプションプランを比較。チャットボットの利用回数、'
              'フローチャート、翻訳、印刷、GMスクリプトなどの特典を確認。',
        'de': 'Vergleiche Tabuneys Free-, Mitglieder- und Abo-Pläne — Chatbot-Anfragelimits, '
              'Flussdiagramm-Zugriff, Übersetzungen, Druck und GM-Skripte.',
        'fr': "Comparez les offres Gratuit, Membre et Abonné de Tabuney : quotas de questions au chatbot, "
              "accès aux organigrammes, traductions, impression et scripts de MJ.",
        'es': 'Compara los planes Gratis, Miembro y Suscriptor de Tabuney: límites de consultas al chatbot, '
              'acceso a diagramas de flujo, traducciones, impresión y guiones de GM.',
    },
    'seo.collection.description': {
        'en': 'Manage your personal board game collection on Tabuney — track owned, '
              'wishlisted and played games with your own ratings and notes.',
        'zh': '在 Tabuney 管理你的個人桌遊收藏——記錄已擁有、想要與玩過的遊戲，並加上自己的評分與備註。',
        'ja': 'Tabuneyで自分のボードゲームコレクションを管理。所有・欲しい・プレイ済みのゲームを'
              '自分の評価やメモとともに記録できます。',
        'de': 'Verwalte deine persönliche Brettspielsammlung auf Tabuney — behalte den Überblick über '
              'besessene, gewünschte und gespielte Spiele mit eigenen Bewertungen und Notizen.',
        'fr': 'Gérez votre collection personnelle de jeux de société sur Tabuney : suivez les jeux possédés, '
              'souhaités et joués avec vos propres notes et évaluations.',
        'es': 'Gestiona tu colección personal de juegos de mesa en Tabuney: lleva el control de los juegos '
              'que posees, deseas y has jugado con tus propias valoraciones y notas.',
    },
    'seo.about.description': {
        'en': 'About Tabuney — our vision, values and mission to help every table '
              'get more playtime out of board games.',
        'zh': '關於 Tabuney——我們的願景、價值觀與使命，幫助每張桌子從桌遊中玩到更多時光。',
        'ja': 'Tabuneyについて——すべてのテーブルがボードゲームをもっと楽しめるように。'
              '私たちのビジョン、価値観、そしてミッション。',
        'de': 'Über Tabuney — unsere Vision, Werte und Mission, jedem Spieltisch mehr Spielzeit '
              'mit Brettspielen zu ermöglichen.',
        'fr': 'À propos de Tabuney — notre vision, nos valeurs et notre mission : aider chaque table '
              'à tirer le meilleur parti des jeux de société.',
        'es': 'Sobre Tabuney: nuestra visión, valores y misión de ayudar a cada mesa a sacar '
              'más partido a los juegos de mesa.',
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
        ('translation', '0012_remove_seo_default_title'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
