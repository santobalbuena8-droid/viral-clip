#!/usr/bin/env bash
# Video sintético de 60s, 16:9, tono senoidal. No usa música comercial.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/data/fixtures/sample_60s.mp4}"
mkdir -p "$(dirname "$OUT")"

if [[ -f "$OUT" ]]; then
  DURATION="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT" || true)"
  if python3 -c 'import sys
try:
    value = float(sys.argv[1])
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if 55 <= value <= 65 else 1)' "$DURATION"; then
    echo "Fixture listo: $OUT"
    exit 0
  fi
fi

SOURCE="testsrc2=size=1280x720:rate=30:duration=60"
if ! ffmpeg -hide_banner -f lavfi -i "$SOURCE" -frames:v 1 -f null - >/dev/null 2>&1; then
  SOURCE="testsrc=size=1280x720:rate=30:duration=60"
fi

ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "$SOURCE" \
  -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=60" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 128k -shortest \
  "$OUT"

echo "Fixture generado: $OUT"
