# feed/services/work_service.py
from django.db import transaction

def mark_irrelevant(work):
    """
    Mark a work as irrelevant and update rss stats atomically
    """
    with transaction.atomic():
        work.irrelevant += 1
        work.save(update_fields=['irrelevant'])

        rss = work.rss
        rss.total_irrelevant += 1
        rss.save(update_fields=['total_irrelevant'])