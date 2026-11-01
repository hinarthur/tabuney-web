import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('commerce', '0003_transaction_invoice_id_transaction_payment_intent_id_and_more'),
    ]
    operations = [migrations.CreateModel(
        name='CheckoutConsent',
        fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('request_key', models.CharField(max_length=64, unique=True)),
            ('kind', models.CharField(max_length=32)),
            ('product_id', models.CharField(blank=True, max_length=64)),
            ('product_label', models.TextField()),
            ('language', models.CharField(max_length=10)),
            ('version', models.CharField(max_length=32)),
            ('digital_text', models.TextField()),
            ('service_text', models.TextField()),
            ('terms_text', models.TextField()),
            ('terms_html', models.TextField()),
            ('privacy_html', models.TextField()),
            ('confirmed_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ('stripe_session_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
            ('confirmation_email', models.EmailField(max_length=254)),
            ('confirmation_sent_at', models.DateTimeField(blank=True, null=True)),
            ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
        ],
        options={'ordering': ['-confirmed_at']},
    )]
