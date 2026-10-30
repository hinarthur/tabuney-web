from django.apps import AppConfig


class FeedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'feed'

    def ready(self):
        # from .tasks import schedule_fetch_rss
        # schedule_fetch_rss()
        pass