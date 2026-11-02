"""問卷進度文字。{n}＝已答題數、{total}＝總題數，由 survey.js 代入。"""

from django.db import migrations

STRINGS = {
    'feedback.survey.progress': {
        'en': 'Answered {n} of {total}',
        'zh': '已回答 {n} / {total} 題',
        'ja': '{total} 問中 {n} 問に回答済み',
        'de': '{n} von {total} beantwortet',
        'fr': '{n} réponse(s) sur {total}',
        'es': '{n} de {total} respondidas',
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
        ('translation', '0057_survey_fab_cta'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
