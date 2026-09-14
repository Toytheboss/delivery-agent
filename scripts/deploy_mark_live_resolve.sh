#!/usr/bin/env bash
# Deploy mark-live disambiguation to production (delivery-agent + QA bot).
# Usage:
#   export SSHPASS='...'   # or use SSH key
#   ./scripts/deploy_mark_live_resolve.sh
set -euo pipefail

HOST="${DEPLOY_HOST:-root@8.222.166.120}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FILES=(
  bot/workflow_mark_live.py
  bot/handlers.py
  bot/metrics.py
  bot/triggers.py
  bot/rag.py
)

ssh_cmd() {
  if [[ -n "${SSHPASS:-}" ]]; then
    sshpass -e ssh -o IPQoS=none -o PreferredAuthentications=password \
      -o PubkeyAuthentication=no -o ConnectTimeout=20 "$HOST" "$@"
  else
    ssh -o ConnectTimeout=20 "$HOST" "$@"
  fi
}

scp_cmd() {
  if [[ -n "${SSHPASS:-}" ]]; then
    sshpass -e scp -o IPQoS=none -o PreferredAuthentications=password \
      -o PubkeyAuthentication=no -o ConnectTimeout=20 "$@"
  else
    scp -o ConnectTimeout=20 "$@"
  fi
}

echo "Uploading to $HOST ..."
for f in "${FILES[@]}"; do
  scp_cmd "$ROOT/$f" "$HOST:/tmp/$(basename "$f")"
done

ssh_cmd 'bash -s' <<'EOF'
set -euo pipefail
TS=$(date +%Y%m%d%H%M%S)
for dest in /opt/delivery-agent /opt/botchain-qa-tg-bot; do
  [[ -d "$dest/bot" ]] || continue
  for f in workflow_mark_live.py handlers.py metrics.py triggers.py rag.py; do
    if [[ -f "$dest/bot/$f" ]]; then
      cp -a "$dest/bot/$f" "$dest/bot/${f}.bak-marklive-resolve-$TS"
    fi
    install -m 644 "/tmp/$f" "$dest/bot/$f"
    chown botuser:botuser "$dest/bot/$f" 2>/dev/null || true
    echo "updated $dest/bot/$f"
  done
done
systemctl restart delivery-agent botchain-qa
sleep 2
systemctl is-active delivery-agent botchain-qa
EOF

echo "Done."
