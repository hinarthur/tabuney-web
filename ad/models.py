import uuid
from django.db import models
from django.utils import timezone
from translation.models import Tribe

def artwork_image_path(instance, filename):
    """
    生成 Artwork 圖片儲存路徑：ad/artwork/YYYY/MM/<uuid>.<ext>
    不依賴 title，確保絕對唯一且分類儲存。
    """
    ext = filename.split('.')[-1]
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    return f"ad/artwork/{timezone.now().strftime('%Y/%m')}/{new_filename}"

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Artwork(TimeStampedModel):
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to=artwork_image_path)
    prompt = models.TextField(blank=True, help_text="Prompt used to generate this artwork")

    def __str__(self):
        return self.title

class Affiliate(TimeStampedModel):
    name = models.CharField(max_length=200)
    artwork = models.ForeignKey(Artwork, on_delete=models.SET_NULL, null=True, related_name='affiliates')
    search_key = models.CharField(max_length=100, help_text="Key to match games or categories (e.g. 'cafe')")
    url = models.URLField(max_length=500, help_text="Destination URL (e.g. Amazon OneLink)")
    is_active = models.BooleanField(default=True)
    cta_name = models.CharField(max_length=100, blank=True, help_text="Match this with the 'name' in CallToAction to pick the button text")

    def __str__(self):
        return self.name

class CallToAction(TimeStampedModel):
    name = models.CharField(max_length=100, help_text="Internal name for this CTA (e.g. 'Amazon Shop')")
    text = models.CharField(max_length=100, help_text="The actual text shown on the button")
    tribe = models.ForeignKey(Tribe, on_delete=models.CASCADE, related_name='ctas')

    def __str__(self):
        return f"{self.name} ({self.tribe.name})"

class AdClick(TimeStampedModel):
    affiliate = models.ForeignKey(Affiliate, on_delete=models.CASCADE, related_name='clicks', null=True, blank=True)
    referer = models.URLField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"Click on {self.affiliate.name} at {self.created_at}"
