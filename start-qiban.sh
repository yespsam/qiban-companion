#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/ai-companion/project"
RUN_DIR="$ROOT/.run"
STATIC_PORT="${QIBAN_STATIC_PORT:-8765}"
API_PORT="${QIBAN_API_PORT:-8766}"
HOST="${QIBAN_HOST:-127.0.0.1}"

mkdir -p "$RUN_DIR"

is_listening() {
  lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

stop_port() {
  local port="$1"
  if is_listening "$port"; then
    echo "重启 $port 端口上的旧服务..."
    lsof -tiTCP:"$port" -sTCP:LISTEN | xargs kill >/dev/null 2>&1 || true
    sleep 1
  fi
}

wait_for_http() {
  local url="$1"
  python3 - "$url" <<'PY'
import sys
import time
import urllib.request

url = sys.argv[1]
deadline = time.time() + 45
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            if response.status < 500:
                raise SystemExit(0)
    except Exception:
        time.sleep(0.5)
raise SystemExit(1)
PY
}

ensure_python_deps() {
  cd "$BACKEND"
  if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv
  fi
  if ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import yaml
import fastapi
import uvicorn
import edge_tts
PY
  then
    .venv/bin/python -m pip install -U pip
    .venv/bin/python -m pip install -r requirements-core.txt edge-tts
  fi
}

BACKEND_PID=""
STATIC_PID=""

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then kill "$BACKEND_PID" >/dev/null 2>&1 || true; fi
  if [ -n "${STATIC_PID:-}" ]; then kill "$STATIC_PID" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

echo "栖伴正在启动..."

if [ "${QIBAN_REUSE_PORTS:-0}" != "1" ]; then
  stop_port "$API_PORT"
  stop_port "$STATIC_PORT"
fi

ensure_python_deps
(
  cd "$BACKEND"
  PYTHONPATH="$BACKEND" .venv/bin/python run.py --ui web --host "$HOST" --port "$API_PORT"
) > "$RUN_DIR/backend.log" 2>&1 &
BACKEND_PID="$!"
wait_for_http "http://$HOST:$API_PORT/api/state"

(
  cd "$ROOT"
  python3 -m http.server "$STATIC_PORT" --bind "$HOST"
) > "$RUN_DIR/static.log" 2>&1 &
STATIC_PID="$!"
wait_for_http "http://$HOST:$STATIC_PORT/"

MOBILE_URL="http://$HOST:$STATIC_PORT/companion-mobile-demo/"
WALLPAPER_URL="http://$HOST:$STATIC_PORT/desktop-wallpaper/"
CONSOLE_URL="http://$HOST:$API_PORT/"

echo "手机聊天: $MOBILE_URL"
echo "3D 壁纸:  $WALLPAPER_URL"
echo "控制台:   $CONSOLE_URL"

if command -v open >/dev/null 2>&1; then
  open "$MOBILE_URL"
  open "$WALLPAPER_URL"
fi

echo "保持此窗口打开即可持续运行。按 Ctrl+C 停止栖伴。"
while true; do sleep 3600; done
