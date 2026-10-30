from django.urls import reverse
from django.http import HttpResponseRedirect

class SubdomainMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0]  # 去掉端口號，只取域名部分
        if host == 'tablejourney.tabuney.local':
            # 如果是子域名，重新導向到 tablejourney 路徑
            if not request.path.startswith('/tablejourney/'):
                return HttpResponseRedirect('/tablejourney' + request.path)
        return self.get_response(request)


def _rss_mb():
    """目前程序的常駐記憶體（MB）；非 Linux（沒有 /proc）回 None。"""
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) // 1024
    except OSError:
        return None
    return None


class MemoryWatchMiddleware:
    """
    單一請求讓 worker 記憶體漲超過 MEMWATCH_MB（預設 50MB）時記一筆 warning，
    用來找出是哪個 URL 把 VPS 吃爆（看 `docker logs django_app 2>&1 | grep memwatch`，
    log 走 stderr，沒有 2>&1 的話 grep 會漏掉）。
    只量測、不改變任何行為；讀 /proc 一次約數十微秒。
    """

    def __init__(self, get_response):
        import logging
        import os

        self.get_response = get_response
        self.threshold = int(os.getenv('MEMWATCH_MB', 50))
        self.logger = logging.getLogger('memwatch')
        # 每個 worker 第一個請求會首次載入模板與模組（實測 +90MB），不是問題，不記
        self.warmed_up = False

    def __call__(self, request):
        before = _rss_mb()
        response = self.get_response(request)
        if not self.warmed_up:
            self.warmed_up = True
        elif before is not None:
            after = _rss_mb()
            if after is not None and after - before >= self.threshold:
                self.logger.warning(
                    'memwatch +%dMB (%d→%dMB) %s %s',
                    after - before, before, after, request.method, request.get_full_path(),
                )
        return response