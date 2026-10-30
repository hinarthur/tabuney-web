"""
django-q 排程任務。排程本身由 migration 0011 建立（get_or_create），不用手動到
admin 新增。
"""

import shutil
from datetime import timedelta

from django.utils import timezone

from .models import ServerSample

# 跟 deploy/vps/mem-snapshot.sh 的保留量無關：那邊是出事當下的細節，這裡只看走勢
KEEP_DAYS = 14


def _meminfo():
    """回傳 /proc/meminfo 的 {欄位: kB}。"""
    info = {}
    with open('/proc/meminfo') as f:
        for line in f:
            name, _, rest = line.partition(':')
            info[name] = int(rest.split()[0])
    return info


def sample_server():
    mem = _meminfo()
    with open('/proc/loadavg') as f:
        load1, load5 = (float(x) for x in f.read().split()[:2])
    disk = shutil.disk_usage('/')

    ServerSample.objects.create(
        mem_total_mb=mem['MemTotal'] // 1024,
        mem_available_mb=mem['MemAvailable'] // 1024,
        swap_used_mb=(mem['SwapTotal'] - mem['SwapFree']) // 1024,
        load1=load1,
        load5=load5,
        disk_used_pct=round(disk.used / disk.total * 100, 1),
    )
    ServerSample.objects.filter(
        created_at__lt=timezone.now() - timedelta(days=KEEP_DAYS)
    ).delete()
