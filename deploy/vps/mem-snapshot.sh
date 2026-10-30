#!/bin/bash
# 記憶體事故快照：可用 RAM 太少或 swap 用太多時，記下「誰在吃記憶體、當下在處理哪些 URL」。
# 由 mem-snapshot.timer 每 60 秒執行；平常什麼都不寫。
# 查看：less /var/log/mem-snapshot.log
set -u

LOG=/var/log/mem-snapshot.log
NGINX_LOG="${NGINX_LOG:-/var/log/nginx/access.log}"
MIN_AVAIL_PCT="${MIN_AVAIL_PCT:-15}"    # 可用 RAM 低於總量的 15%
MAX_SWAP_MB="${MAX_SWAP_MB:-1200}"      # 或 swap 用量超過 1.2GB

mem_total=$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo)
mem_avail=$(awk '/^MemAvailable:/ {print int($2/1024)}' /proc/meminfo)
swap_total=$(awk '/^SwapTotal:/ {print int($2/1024)}' /proc/meminfo)
swap_free=$(awk '/^SwapFree:/ {print int($2/1024)}' /proc/meminfo)
swap_used=$((swap_total - swap_free))
avail_pct=$((mem_avail * 100 / mem_total))

if [ "$avail_pct" -ge "$MIN_AVAIL_PCT" ] && [ "$swap_used" -le "$MAX_SWAP_MB" ]; then
    exit 0
fi

{
    echo "===== $(date '+%F %T') avail=${mem_avail}MB(${avail_pct}%) swap_used=${swap_used}MB ====="
    free -m
    echo "--- 前 15 大程序（RSS）"
    ps -eo pid,rss,etime,args --sort=-rss | head -16 | cut -c1-200
    echo "--- 各容器 cgroup 記憶體（current / peak / swap，MB）"
    for id in $(docker ps -q --no-trunc 2>/dev/null); do
        d=/sys/fs/cgroup/system.slice/docker-$id.scope
        [ -d "$d" ] || continue
        name=$(docker inspect -f '{{.Name}}' "$id" 2>/dev/null)
        printf '%-28s cur=%5dM peak=%5dM swap=%5dM\n' "$name" \
            $(( $(cat "$d/memory.current") / 1048576 )) \
            $(( $(cat "$d/memory.peak" 2>/dev/null || echo 0) / 1048576 )) \
            $(( $(cat "$d/memory.swap.current" 2>/dev/null || echo 0) / 1048576 ))
    done
    if [ -r "$NGINX_LOG" ]; then
        echo "--- nginx 最近 1000 筆請求，最常見的 20 個 URL"
        tail -n 1000 "$NGINX_LOG" | awk '{print $7}' | sort | uniq -c | sort -rn | head -20
        echo "--- 最近 1000 筆請求，最常見的 10 個 User-Agent"
        tail -n 1000 "$NGINX_LOG" | awk -F'"' '{print $6}' | sort | uniq -c | sort -rn | head -10 | cut -c1-160
    fi
    echo "--- django memwatch（最近 5 分鐘）"
    docker logs --since 5m django_app 2>&1 | grep memwatch | tail -20
    echo
} >> "$LOG" 2>&1
