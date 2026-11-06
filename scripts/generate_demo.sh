#!/usr/bin/env sh
# Video de muestra de 45 s (640x360, ~2 MB) para «Probar con muestra». Sin música comercial.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/demo/muestra_45s.mp4}"
mkdir -p "$(dirname "$OUT")"
if [ -s "$OUT" ]; then
  echo "Muestra lista: $OUT"
  exit 0
fi
ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "testsrc2=size=640x360:rate=24:duration=45" \
  -f lavfi -i "sine=frequency=330:sample_rate=44100:duration=45" \
  -vf "hue=H=t*0.4" \
  -c:v libx264 -preset slow -crf 34 -pix_fmt yuv420p \
  -c:a aac -b:a 48k -shortest -movflags +faststart "$OUT"
echo "Muestra generada: $OUT"
