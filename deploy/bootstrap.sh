#!/usr/bin/env bash
# Idempotent-ish Ubuntu bootstrap for Delivery Agent.
# Usage (on the VPS, as root or with sudo):
#   sudo bash deploy/bootstrap.sh [/opt/delivery-agent]
set -euo pipefail

APP_DIR="${1:-/opt/delivery-agent}"
APP_USER="${APP_USER:-botuser}"

echo "==> Installing OS packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  python3 \
  python3-venv \
  python3-pip \
  git \
  curl \
  ca-certificates \
  build-essential

# Playwright Chromium system deps (Ubuntu 22.04/24.04). Safe to re-run.
# Full list may grow with Playwright versions; prefer `playwright install-deps` after venv exists.
if command -v apt-get >/dev/null 2>&1; then
  apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    || true
fi

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  echo "==> Creating user: $APP_USER"
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "==> Creating app dir: $APP_DIR"
  mkdir -p "$APP_DIR"
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Bootstrap done."
echo "Next:"
echo "  1) Copy project + .env + session into $APP_DIR (as $APP_USER)"
echo "  2) sudo -u $APP_USER bash -lc 'cd $APP_DIR && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && playwright install chromium'"
echo "  3) Optionally: sudo $APP_DIR/.venv/bin/playwright install-deps chromium"
echo "  4) Install systemd unit from deploy/delivery-agent.service"
echo "  5) Stop local bot BEFORE starting systemd (one Telegram session only)"
