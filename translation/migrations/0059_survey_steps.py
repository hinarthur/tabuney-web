"""問卷「一個版面一題」的導覽文字。{n}＝目前第幾題、{total}＝總題數，由 survey.js 代入。"""

from django.db import migrations

STRINGS = {
    'feedback.survey.step': {
        'en': 'Question {n} of {total}',
        'zh': '第 {n} / {total} 題',
        'ja': '質問 {n} / {total}',
        'de': 'Frage {n} von {total}',
        'fr': 'Question {n} sur {total}',
        'es': 'Pregunta {n} de {total}',
    },
    'feedback.survey.next': {
        'en': 'Next',
        'zh': '下一題',
        'ja': '次へ',
        'de': 'Weiter',
        'fr': 'Suivant',
        'es': 'Siguiente',
    },
    'feedback.survey.back': {
        'en': 'Back',
        'zh': '上一題',
        'ja': '戻る',
        'de': 'Zurück',
        'fr': 'Précédent',
        'es': 'Atrás',
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
        ('translation', '0058_survey_progress'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
