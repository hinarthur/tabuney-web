"""
首頁 hero 改版（左文案＋搜尋，右 Full Flowchart / Step Flow 疊卡）新增的字串。
標題沿用舊的 slogan.less_learn_more_enjoy 會被 SEO title 共用，
所以 hero 用自己的 home.hero.title_1 / title_2。
"""

from django.db import migrations

STRINGS = {
    'home.hero.eyebrow': {
        'en': 'Visual board game guides',
        'zh': '視覺化桌遊指南',
        'ja': 'ビジュアルで学ぶボードゲームガイド',
        'de': 'Visuelle Brettspiel-Anleitungen',
        'fr': 'Guides visuels de jeux de société',
        'es': 'Guías visuales de juegos de mesa',
    },
    'home.hero.title_1': {
        'en': 'Less Time on Rules,',
        'zh': '少花時間讀規則，',
        'ja': 'ルール確認は短く、',
        'de': 'Weniger Regeln lesen,',
        'fr': 'Moins de temps sur les règles,',
        'es': 'Menos tiempo con las reglas,',
    },
    'home.hero.title_2': {
        'en': 'More Time to Play',
        'zh': '多點時間開玩',
        'ja': 'もっと遊ぶ時間を',
        'de': 'mehr Zeit zum Spielen',
        'fr': 'plus de temps pour jouer',
        'es': 'más tiempo para jugar',
    },
    'home.hero.lead': {
        'en': 'Understand tabletop games with visual flowcharts, clear rule answers, and ready-to-use teaching scripts. Get everyone to the table faster.',
        'zh': '用視覺化流程圖、清楚的規則解答與現成的教學講稿看懂桌遊，讓大家更快上桌開玩。',
        'ja': 'ビジュアルなフローチャート、わかりやすいルール回答、すぐ使える説明スクリプトでボードゲームを理解。みんなですばやくテーブルを囲めます。',
        'de': 'Verstehe Brettspiele mit visuellen Flussdiagrammen, klaren Regelantworten und sofort einsetzbaren Erklärskripten. So sitzen alle schneller am Tisch.',
        'fr': 'Comprenez les jeux de société grâce à des organigrammes visuels, des réponses claires sur les règles et des scripts d’explication prêts à l’emploi. Tout le monde à table plus vite.',
        'es': 'Entiende los juegos de mesa con diagramas de flujo visuales, respuestas claras sobre las reglas y guiones de enseñanza listos para usar. Sienta a todos a la mesa más rápido.',
    },
    'home.hero.feature_flowcharts': {
        'en': 'Flowcharts',
        'zh': '流程圖',
        'ja': 'フローチャート',
        'de': 'Flussdiagramme',
        'fr': 'Organigrammes',
        'es': 'Diagramas de flujo',
    },
    'home.hero.feature_rulesbot': {
        'en': 'Rulesbot',
        'zh': '規則機器人',
        'ja': 'ルールボット',
        'de': 'Regelbot',
        'fr': 'Rulesbot',
        'es': 'Rulesbot',
    },
    'home.hero.feature_scripts': {
        'en': 'Guide Scripts',
        'zh': '教學講稿',
        'ja': '説明スクリプト',
        'de': 'Erklärskripte',
        'fr': 'Scripts d’explication',
        'es': 'Guiones de enseñanza',
    },
    'home.hero.feature_languages': {
        'en': '6 languages',
        'zh': '6 種語言',
        'ja': '6言語対応',
        'de': '6 Sprachen',
        'fr': '6 langues',
        'es': '6 idiomas',
    },
    'home.hero.tag_full': {
        'en': 'Full Flowchart · 6 nimmt!',
        'zh': '完整流程圖 · 6 nimmt!',
        'ja': '全体フローチャート · 6 nimmt!',
        'de': 'Gesamtdiagramm · 6 nimmt!',
        'fr': 'Organigramme complet · 6 nimmt!',
        'es': 'Diagrama completo · 6 nimmt!',
    },
    'home.hero.tag_step': {
        'en': 'Step Flow · 6 nimmt!',
        'zh': '逐步流程 · 6 nimmt!',
        'ja': 'ステップフロー · 6 nimmt!',
        'de': 'Schritt für Schritt · 6 nimmt!',
        'fr': 'Pas à pas · 6 nimmt!',
        'es': 'Paso a paso · 6 nimmt!',
    },
    'home.hero.note_1': {
        'en': 'See the Big Picture.',
        'zh': '看清全貌，',
        'ja': '全体像をつかみ、',
        'de': 'Das große Ganze sehen.',
        'fr': 'Voyez l’ensemble.',
        'es': 'Mira el panorama completo.',
    },
    'home.hero.note_2': {
        'en': 'Follow Every Step.',
        'zh': '一步步跟著走。',
        'ja': '一歩ずつたどれる。',
        'de': 'Jeden Schritt folgen.',
        'fr': 'Suivez chaque étape.',
        'es': 'Sigue cada paso.',
    },
    'home.hero.caption_branch': {
        'en': 'Choose a Branch:',
        'zh': '選擇分支：',
        'ja': '分岐を選択：',
        'de': 'Zweig wählen:',
        'fr': 'Choisir une branche :',
        'es': 'Elige una rama:',
    },
    'home.hero.caption_sequence': {
        'en': 'Step Flow · Follow the sequence',
        'zh': '逐步流程 · 依序前進',
        'ja': 'ステップフロー · 順番に進む',
        'de': 'Schritt für Schritt · der Reihe nach',
        'fr': 'Pas à pas · suivez la séquence',
        'es': 'Paso a paso · sigue la secuencia',
    },
    'home.hero.caption_end': {
        'en': 'Game complete',
        'zh': '遊戲結束',
        'ja': 'ゲーム終了',
        'de': 'Spiel beendet',
        'fr': 'Partie terminée',
        'es': 'Juego completado',
    },
    'home.hero.nav_first': {
        'en': 'First step',
        'zh': '第一步',
        'ja': '最初のステップ',
        'de': 'Erster Schritt',
        'fr': 'Première étape',
        'es': 'Primer paso',
    },
    'home.hero.nav_prev': {
        'en': 'Previous step',
        'zh': '上一步',
        'ja': '前のステップ',
        'de': 'Vorheriger Schritt',
        'fr': 'Étape précédente',
        'es': 'Paso anterior',
    },
    'home.hero.nav_next': {
        'en': 'Next step',
        'zh': '下一步',
        'ja': '次のステップ',
        'de': 'Nächster Schritt',
        'fr': 'Étape suivante',
        'es': 'Paso siguiente',
    },
    'home.hero.nav_last': {
        'en': 'Last step',
        'zh': '最後一步',
        'ja': '最後のステップ',
        'de': 'Letzter Schritt',
        'fr': 'Dernière étape',
        'es': 'Último paso',
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
        ('translation', '0041_rulebook_source_unavailable_string'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
