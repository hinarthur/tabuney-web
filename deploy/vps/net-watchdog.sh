#!/bin/bash
# 網路 watchdog：ens6 沒有 IPv4 或沒有 default route 時，自動 networkctl reconfigure。
# 背景：RAM 爆掉時 DHCP 續約失敗，網路不會自己恢復（2026-10 事故）。
# 這不解決 RAM 問題，只是讓網站在記憶體恢復後自己回來。
# 由 net-watchdog.timer 每 60 秒執行；查紀錄：journalctl -t net-watchdog
set -u

IFACE="${IFACE:-ens6}"
TAG="net-watchdog"

has_ipv4() { ip -4 addr show dev "$IFACE" 2>/dev/null | grep -q 'inet '; }
has_route() { ip route show default 2>/dev/null | grep -q .; }

if has_ipv4 && has_route; then
    exit 0
fi

logger -t "$TAG" "網路異常：ipv4=$(has_ipv4 && echo ok || echo MISSING) default_route=$(has_route && echo ok || echo MISSING)，執行 networkctl reconfigure $IFACE"
# 留下當下的記憶體狀態，方便事後對照是不是 RAM 造成的
logger -t "$TAG" "$(free -m | tr '\n' ' ')"

networkctl reconfigure "$IFACE"
sleep 15

if has_ipv4 && has_route; then
    logger -t "$TAG" "已恢復：$(ip -4 -brief addr show dev "$IFACE")"
else
    # 刻意不自動重開機：避免網路以外的原因造成無限 reboot。下一輪 timer 會再試。
    logger -t "$TAG" "reconfigure 後仍未恢復，等下一輪再試"
fi
