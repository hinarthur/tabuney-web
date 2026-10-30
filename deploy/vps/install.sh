#!/bin/bash
# 在 VPS 上以 root 執行一次：sudo bash deploy/vps/install.sh
# 安裝：網路 watchdog、記憶體事故快照、sysstat（sar 歷史紀錄）、earlyoom、swappiness=10。
# 可重複執行（每次覆蓋成最新版）。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

install -m 755 "$HERE/net-watchdog.sh" /usr/local/bin/net-watchdog.sh
install -m 755 "$HERE/mem-snapshot.sh" /usr/local/bin/mem-snapshot.sh

for name in net-watchdog mem-snapshot; do
    cat > /etc/systemd/system/$name.service <<EOF
[Unit]
Description=$name (tablejourney)

[Service]
Type=oneshot
ExecStart=/usr/local/bin/$name.sh
EOF
    cat > /etc/systemd/system/$name.timer <<EOF
[Unit]
Description=Run $name every minute

[Timer]
OnBootSec=2min
OnUnitActiveSec=60s
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF
done

# 快照 log 每週輪替、保留 4 份
cat > /etc/logrotate.d/mem-snapshot <<'EOF'
/var/log/mem-snapshot.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
EOF

# swap 已有 2GB；降低 swappiness，減少「還沒滿就拚命換頁」造成的 thrashing
echo 'vm.swappiness=10' > /etc/sysctl.d/90-tablejourney.conf
sysctl -p /etc/sysctl.d/90-tablejourney.conf

apt-get update -qq
apt-get install -y -qq sysstat earlyoom

# sar：每 10 分鐘記一次（Ubuntu 預設），開啟收集
sed -i 's/^ENABLED=.*/ENABLED="true"/' /etc/default/sysstat
systemctl enable --now sysstat

# earlyoom：RAM 可用 < 5% 且 swap 剩 < 30% 時，提早殺最大的程序（優先 gunicorn），
# 避免系統卡死到連網路一起掛；保護 sshd / 網路 / docker / postgres。
cat > /etc/default/earlyoom <<'EOF'
EARLYOOM_ARGS="-m 5 -s 30 -r 3600 --prefer '(^|/)(gunicorn|python)$' --avoid '(^|/)(sshd|systemd|systemd-networkd|systemd-journald|dockerd|containerd|postgres)$'"
EOF
systemctl enable earlyoom
systemctl restart earlyoom

systemctl daemon-reload
systemctl enable --now net-watchdog.timer mem-snapshot.timer

echo
echo "完成。檢查："
systemctl list-timers --no-pager | grep -E 'net-watchdog|mem-snapshot' || true
systemctl is-active earlyoom sysstat
