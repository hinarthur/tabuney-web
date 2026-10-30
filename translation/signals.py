from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Translation, Tribe
from django.core.cache import cache

@receiver([post_save, post_delete], sender=Translation)
def clear_translation_cache(sender, instance, **kwargs):
    # 只清受影響語言。cache key 必須用 language（語言碼），不能用 name：
    # TranslationListView 是以 f'translation_{lang}' 存的，name（如 'zh - 華文'）
    # 組出來的 key 對不上，清了等於沒清，還會因為含空白觸發 CacheKeyWarning。
    lang = instance.tribe.language
    if not lang:
        return
    cache_key = f'translation_{lang}'
    cache.delete(cache_key)

@receiver([post_save, post_delete], sender=Tribe)
def clear_tribe_translation_cache(sender, instance, **kwargs):
    lang = instance.language
    if not lang:
        return
    cache_key = f'translation_{lang}'
    cache.delete(cache_key)