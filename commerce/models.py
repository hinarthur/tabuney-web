from django.db import models
from django.utils import timezone

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        
class Currency(TimeStampedModel):
    """貨幣管理"""
    code = models.CharField(
        max_length=3, 
        unique=True,
        help_text="ISO 4217 code (e.g., USD, EUR, TWD)"
    )
    symbol = models.CharField(max_length=10, help_text="Currency symbol (e.g., $, €, NT$)")
    name = models.CharField(max_length=50, help_text="Full currency name")
   
    class Meta:
        verbose_name_plural = "Currencies"
        ordering = ['code']
    
    def __str__(self):
        return f"{self.code} ({self.symbol})"

class Transaction(TimeStampedModel):
    member = models.ForeignKey('member.Member', on_delete=models.SET_NULL, null=True, related_name='transactions', help_text="關聯的會員")
    stripe_session_id = models.CharField(max_length=255, unique=True, help_text="Stripe Checkout Session ID")
    payment_intent_id = models.CharField(max_length=255, null=True, blank=True, help_text="Stripe PaymentIntent ID")
    invoice_id = models.CharField(max_length=255, null=True, blank=True, help_text="Stripe Invoice ID")
    customer_id = models.CharField(max_length=255, null=True, blank=True, help_text="Stripe Customer ID")
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="交易金額")
    currency = models.CharField(max_length=10, help_text="交易幣別")
    status = models.CharField(max_length=50, help_text="交易狀態，例如 complete")

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-created_at']

    def __str__(self):
        return f"Transaction {self.id} - {self.status} - {self.member}"

class Subscription(TimeStampedModel):
    member = models.OneToOneField('member.Member', on_delete=models.CASCADE, related_name='subscription')
    stripe_subscription_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=50, help_text="例如 active, past_due, canceled 等")
    current_period_start = models.DateTimeField(help_text="本期開始時間")
    current_period_end = models.DateTimeField(help_text="本期結束時間")
    cancel_at_period_end = models.BooleanField(default=False, help_text="是否於這期結束時取消")
    
    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        ordering = ['-current_period_end']
        
    def __str__(self):
        return f"{self.member} - {self.status}"
