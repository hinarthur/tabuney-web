# feed/web_views.py
from django.shortcuts import render, get_object_or_404
from .models import Work, SavedWork
from stats.utils import log_page_visit

def feed_page(request):
    log_page_visit(request, 'feed_list')
    return render(request, 'feed/feed_list.html')

def feed_detail_page(request, pk):
    work = get_object_or_404(Work.objects.select_related('rss'), pk=pk)

    saved = False
    saved_work_id = None
    if request.user.is_authenticated:
        try:
            member = request.user.member
            sw = SavedWork.objects.filter(member=member, work=work).first()
            if sw:
                saved = True
                saved_work_id = sw.id
        except Exception:
            # if Member doesn't exist or other issues, treat as not saved
            saved = False
            saved_work_id = None

    return render(request, 'feed/feed_detail.html', {
        'work': work,
        'saved': saved,
        'saved_work_id': saved_work_id,
    })