#!/usr/bin/env bash
# Pipeline en primer plano, sin levantar el servidor.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

bash "$ROOT/scripts/generate_fixture.sh"
set +e
JSON="$(python -m app.cli --local "$ROOT/data/fixtures/sample_60s.mp4" --max-clips 2)"
CODE=$?
set -e
if [[ -z "$JSON" ]]; then
  echo "El pipeline no devolvió JSON (código $CODE)." >&2
  exit 1
fi
printf '%s\n' "$JSON" | python -m json.tool
python - "$JSON" << 'PY'
import json, subprocess, sys

job = json.loads(sys.argv[1])
if job["status"] != "completed":
    raise SystemExit(job.get("error") or "El job no terminó.")
ready = [clip for clip in job["clips"] if clip["status"] == "ready" and clip.get("output_path")]
if not ready:
    raise SystemExit("No hay clips listos.")
path = ready[0]["output_path"]
raw = subprocess.check_output(
    [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,pix_fmt,codec_name",
        "-of", "json", path,
    ],
    text=True,
)
stream = json.loads(raw)["streams"][0]
width, height = int(stream["width"]), int(stream["height"])
print(f"{path}")
print(f"{width}x{height} pix_fmt={stream['pix_fmt']} codec={stream['codec_name']}")
if stream["pix_fmt"] != "yuv420p" or stream["codec_name"] != "h264":
    raise SystemExit("El clip no es h264 yuv420p.")
if abs((width / height) - (9 / 16)) > 0.01:
    raise SystemExit(f"El aspecto {width}x{height} no es 9:16.")
print("OK clip vertical 9:16")
PY
