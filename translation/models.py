# translation/models.py

from django.db import models

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        
class Tribe(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    language = models.CharField(max_length=10, null=True, blank=True, unique=True)
    
    def __str__(self):
        return self.name
    
class Translation(models.Model):
    tribe = models.ForeignKey(
        Tribe, 
        on_delete=models.CASCADE, 
        related_name='translations'
    )
    key = models.CharField(max_length=100)
    # blank=True：空字串是合法譯文，不是漏填。中日文語序把遊戲名放句首，
    # 所以 seo.game.*.desc.prefix 這類「前綴」在 zh/ja 本來就該是空的，
    # 意思全部落在 suffix。少了 blank=True，admin 的 ModelForm 會擋下
    # 「This field is required.」——而 list_editable 是一整個 formset，
    # 一列無效就整頁存不了，連同頁其他列的修改一起被打回。
    value = models.TextField(blank=True)
    is_synced = models.BooleanField(default=False)  # 是否已同步到 VPS
    synced_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(null=True, default=None)  # None=尚未掃描, True/False=掃描結果
    used_checked_at = models.DateTimeField(null=True, blank=True)  # 最後一次掃描時間

    def save(self, *args, **kwargs):
        if self.pk:
            old = Translation.objects.get(pk=self.pk)
            if old.value != self.value:
                self.is_synced = False
                self.synced_at = None
        super().save(*args, **kwargs)
        
    class Meta:
        unique_together = ('tribe', 'key')  # 确保唯一性

    def __str__(self):
        return f"{self.tribe.name}: {self.key}"
   
class Region(TimeStampedModel):
    # 建議用短 code：tw/hk/cn/jp/eu/global...（你也可以用 ISO-3166）
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.code})"    

# === Signal for auto cache clearing ===
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

@receiver([post_save, post_delete], sender=Translation)
def clear_translation_cache(sender, instance, **kwargs):
    # instance.tribe.language 可能為 None，務必檢查
    if instance.tribe and instance.tribe.language:
        cache_key = f'translation_{instance.tribe.language}'
        cache.delete(cache_key)
        print(f"[CACHE] Cleared {cache_key} due to Translation change")