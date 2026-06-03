#!/usr/bin/env bash
# Demo launcher (Faz 8 Iter 8.1): tek komutla 5 süreç + temiz baseline seed.
# Kullanım: ./scripts/demo_up.sh   (kapatma: ./scripts/demo_down.sh)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
PIDFILE="$ROOT/data/demo.pids"
LOGDIR="$ROOT/logs/demo"

[[ -x "$PY" ]] || { echo "HATA: .venv yok ($PY). Önce: python3.11 -m venv .venv && pip install -r requirements.txt -e ."; exit 1; }

# 1) Cleanup-first: eski demo süreçlerini kapat (çift ingestion / client_id collision'ı önle).
bash "$ROOT/scripts/demo_down.sh" || true
mkdir -p "$ROOT/data" "$LOGDIR"

# 2) Mosquitto: çalışmıyorsa başlat (varsa dokunma).
if ! pgrep -x mosquitto >/dev/null 2>&1; then
  echo "demo_up: mosquitto başlatılıyor..."
  brew services start mosquitto >/dev/null 2>&1 || mosquitto -d || {
    echo "HATA: mosquitto başlatılamadı. Manuel başlatın."; exit 1; }
  sleep 1
fi

# 3) Config'ler: eksik runtime config'leri example'dan; devices/detectors'ı demo'dan (yedekle).
for ex in config/*.yaml.example; do
  rt="${ex%.example}"
  [[ -f "$rt" ]] || cp "$ex" "$rt"
done
for f in devices detectors; do
  [[ -f "config/$f.yaml" ]] && cp "config/$f.yaml" "config/$f.yaml.bak"
  cp "config/$f.demo.yaml" "config/$f.yaml"
done

# 4) DB temizliği: tekrarlanabilir demo (arşivle, sessiz silme yok).
if [[ -f data/telemetry.db ]]; then
  mv -f data/telemetry.db "data/telemetry.db.pre-demo"
  rm -f data/telemetry.db-wal data/telemetry.db-shm
fi

# 5) Temiz baseline seed (istatistik canlı tetiklensin).
echo "demo_up: temiz baseline seed'leniyor..."
PYTHONPATH=src "$PY" scripts/seed_demo_baseline.py

# 6) Servisleri sırayla başlat (arka planda); PID'leri kaydet.
: > "$PIDFILE"
start() {  # start <isim> <komut...>
  local name="$1"; shift
  echo "demo_up: $name başlatılıyor..."
  PYTHONPATH=src "$@" >"$LOGDIR/$name.log" 2>&1 &
  local pid=$!
  echo "$pid $name" >> "$PIDFILE"
  sleep 2
  # Liveness check: arka plan süreci hemen çökerse banner yalan söylemesin (B2).
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "HATA: $name başlatılamadı/çöktü. Son loglar:"
    tail -n 20 "$LOGDIR/$name.log" || true
    bash "$ROOT/scripts/demo_down.sh" || true
    exit 1
  fi
}
start ingestion "$PY" -m ingestion
start detectors "$PY" -m detectors
start simulator "$PY" -m simulator
start dashboard "$PY" -m streamlit run src/dashboard/app.py

echo ""
echo "demo_up: TÜM servisler çalışıyor. Dashboard → http://localhost:8501"
echo "demo_up: loglar → $LOGDIR/   | kapatmak için → ./scripts/demo_down.sh"
