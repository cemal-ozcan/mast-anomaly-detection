#!/usr/bin/env bash
# Demo teardown (Faz 8 Iter 8.1): data/demo.pids'teki süreçleri temiz kapatır. Idempotent.
# Mosquitto'ya DOKUNMAZ (kullanıcının olabilir).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/data/demo.pids"

if [[ ! -f "$PIDFILE" ]]; then
  echo "demo_down: çalışan demo yok (pidfile yok)."
  exit 0
fi

pids=()
while read -r pid name; do
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    echo "demo_down: $name (pid $pid) kapatılıyor..."
    kill -TERM "$pid" 2>/dev/null || true
    pids+=("$pid")
  fi
done < "$PIDFILE"

# Graceful shutdown'a kısa süre tanı (BatchWriter final flush + engine dispose) — S4.
for _ in 1 2 3 4 5; do
  alive=0
  for pid in "${pids[@]:-}"; do [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && alive=1; done
  [[ "$alive" -eq 0 ]] && break
  sleep 1
done

rm -f "$PIDFILE"
echo "demo_down: temiz kapandı."
