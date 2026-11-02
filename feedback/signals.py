"""題目、選項、問卷一有變動就 bump 快取版本號，views._survey_payload 的舊快取自然失效。"""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from feedback.models import Survey, SurveyChoice, SurveyQuestion
from feedback.views import CACHE_VERSION_KEY


@receiver([post_save, post_delete], sender=Survey)
@receiver([post_save, post_delete], sender=SurveyQuestion)
@receiver([post_save, post_delete], sender=SurveyChoice)
def bump_survey_cache_version(**kwargs):
    try:
        cache.incr(CACHE_VERSION_KEY)
    except ValueError:
        cache.set(CACHE_VERSION_KEY, 1, None)
