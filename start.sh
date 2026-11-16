#!/usr/bin/env bash
# Start the backend and frontend together for local development.
# Usage: ./start.sh            (Ctrl+C stops both)
# Environment variables such as APP_PORT or DATA_DIR are passed through to the backend.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
BACKEND_PORT="${APP_PORT:-8000}"
BACKEND_HOST="${APP_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

log() { printf '\033[1;34m[start]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[start]\033[0m %s\n' "$*" >&2; exit 1; }

# --- Node (nvm is not loaded in non-interactive shells) ----------------------
if ! command -v npm >/dev/null 2>&1; then
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
fi
command -v npm >/dev/null 2>&1 || die "npm not found. Install Node.js 22+ (e.g. via nvm)."

# --- First-run setup ----------------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  log "Creating Python virtual environment..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$BACKEND/requirements.txt"
elif [ "$BACKEND/requirements.txt" -nt "$VENV/.requirements-installed" ]; then
  log "Installing backend dependencies..."
  "$VENV/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi
touch "$VENV/.requirements-installed"

if [ ! -d "$FRONTEND/node_modules" ] || [ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]; then
  log "Installing frontend dependencies..."
  (cd "$FRONTEND" && npm install --no-fund --no-audit)
fi

# --- Ports must be free ---------------------------------------------------------
# Otherwise the health check below could be answered by another instance
# (e.g. a second ./start.sh), and the new frontend would talk to its data.
port_in_use() { (exec 3<>"/dev/tcp/$1/$2") 2>/dev/null; }
port_in_use "$BACKEND_HOST" "$BACKEND_PORT" \
  && die "Port $BACKEND_PORT is already in use (is the app already running?). Stop it, or set APP_PORT."
port_in_use 127.0.0.1 "$FRONTEND_PORT" \
  && die "Port $FRONTEND_PORT is already in use (is the app already running?). Stop it, or set FRONTEND_PORT."

# --- Run ----------------------------------------------------------------------
# On Ctrl+C or exit, stop everything this script started.
trap 'trap - INT TERM EXIT; log "Stopping..."; kill 0 2>/dev/null; wait' INT TERM EXIT

log "Starting backend on http://$BACKEND_HOST:$BACKEND_PORT ..."
(cd "$BACKEND" && "$VENV/bin/python" -m app 2>&1 | sed -u 's/^/[backend]  /') &

# Wait for the backend to answer before starting the frontend.
for _ in $(seq 1 30); do
  if curl -sf --noproxy "*" "http://$BACKEND_HOST:$BACKEND_PORT/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
curl -sf --noproxy "*" "http://$BACKEND_HOST:$BACKEND_PORT/api/health" >/dev/null 2>&1 \
  || die "Backend did not become healthy. See the [backend] output above."

export VITE_BACKEND_URL="${VITE_BACKEND_URL:-http://$BACKEND_HOST:$BACKEND_PORT}"
log "Starting frontend..."
(cd "$FRONTEND" && npm run dev -- --clearScreen false --port "$FRONTEND_PORT" --strictPort 2>&1 | sed -u 's/^/[frontend] /') &

log "Ready: open http://127.0.0.1:$FRONTEND_PORT  (API docs: http://$BACKEND_HOST:$BACKEND_PORT/api/docs). Ctrl+C to stop."
wait
