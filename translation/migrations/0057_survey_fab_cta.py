"""
問卷浮動按鈕的 CTA 改版：edition 頁「Guide Feedback」、全站（beta）「Help Shape Tabuney」。
覆蓋 0056 的 feedback.survey.fab.edition / feedback.survey.fab.site。
"""

from django.db import migrations

STRINGS = {
    'feedback.survey.fab.edition': {
        'en': 'Guide Feedback',
        'zh': '回饋這份指南',
        'ja': 'ガイドへのフィードバック',
        'de': 'Feedback zur Anleitung',
        'fr': 'Avis sur le guide',
        'es': 'Opina sobre la guía',
    },
    'feedback.survey.fab.site': {
        'en': 'Help Shape Tabuney',
        'zh': '一起打造 Tabuney',
        'ja': 'Tabuney づくりに参加',
        'de': 'Gestalte Tabuney mit',
        'fr': 'Façonnez Tabuney',
        'es': 'Ayuda a dar forma a Tabuney',
    },
}

PREVIOUS = {
    'feedback.survey.fab.edition': {
        'en': 'Quick survey (1 min)',
        'zh': '1 分鐘小問卷',
        'ja': '1分アンケート',
        'de': 'Kurze Umfrage (1 Min.)',
        'fr': 'Mini-sondage (1 min)',
        'es': 'Encuesta rápida (1 min)',
    },
    'feedback.survey.fab.site': {
        'en': 'Help us improve Tabuney',
        'zh': '幫我們改善 Tabuney',
        'ja': 'Tabuney の改善にご協力ください',
        'de': 'Hilf uns, Tabuney zu verbessern',
        'fr': 'Aidez-nous à améliorer Tabuney',
        'es': 'Ayúdanos a mejorar Tabuney',
    },
}


def _apply(apps, strings):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')
    for key, translations in strings.items():
        for lang, value in translations.items():
            tribe = Tribe.objects.filter(language=lang).first()
            if tribe is None:
                continue
            Translation.objects.update_or_create(
                tribe=tribe, key=key,
                defaults={'value': value, 'is_synced': False},
            )


def forwards(apps, schema_editor):
    _apply(apps, STRINGS)


def backwards(apps, schema_editor):
    _apply(apps, PREVIOUS)


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0056_feedback_survey_strings'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
