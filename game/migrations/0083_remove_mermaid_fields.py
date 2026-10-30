from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0082_scrapedproduct_family_rank_scrapedproduct_party_rank_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="rulebookflowchart",
            name="mermaid_text",
        ),
        migrations.RemoveField(
            model_name="rulebookflowchart",
            name="generation_metadata",
        ),
    ]
