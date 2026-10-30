from django.contrib import admin
from .models import Currency, Transaction, Subscription

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['code', 'symbol', 'name', 'updated_at']
    search_fields = ['code', 'name']

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'member', 'amount', 'currency', 'status', 'created_at']
    search_fields = ['stripe_session_id', 'payment_intent_id', 'invoice_id', 'customer_id', 'member__id__username']
    list_filter = ['status', 'currency', 'created_at']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['member', 'status', 'current_period_start', 'current_period_end', 'cancel_at_period_end']
    search_fields = ['stripe_subscription_id', 'member__id__username']
    list_filter = ['status', 'cancel_at_period_end']
    readonly_fields = ['created_at', 'updated_at']
