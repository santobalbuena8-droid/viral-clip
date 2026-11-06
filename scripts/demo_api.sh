#!/usr/bin/env bash
# Crea un job contra el backend ya arrancado y comprueba el clip 9:16.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8741}"
BASE="${BASE:-http://127.0.0.1:$PORT}"
MAX_CLIPS="${MAX_CLIPS:-2}"
FIXTURE="$ROOT/data/fixtures/sample_60s.mp4"

bash "$ROOT/scripts/generate_fixture.sh" "$FIXTURE"

echo "→ GET $BASE/health"
curl -fsS "$BASE/health"
echo

echo "→ POST $BASE/jobs"
RESP="$(curl -fsS -X POST "$BASE/jobs" \
  -H 'content-type: application/json' \
  -d "{\"local_path\": \"$FIXTURE\", \"max_clips\": $MAX_CLIPS}")"
echo "$RESP" | python3 -m json.tool
ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$RESP")"

JOB=""
STATUS=""
for _ in $(seq 1 90); do
  JOB="$(curl -fsS "$BASE/jobs/$ID")"
  STATUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$JOB")"
  echo "→ $ID $STATUS"
  if [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]]; then
    break
  fi
  sleep 1
done

echo "$JOB" | python3 -m json.tool
if [[ "$STATUS" != "completed" ]]; then
  echo "El job no terminó en completed." >&2
  exit 1
fi

CLIP_PATH="$(python3 -c 'import json,sys; job=json.load(sys.stdin); ready=[c["playback_path"] for c in job["clips"] if c["status"]=="ready" and c.get("playback_path")]; print(ready[0] if ready else "")' <<<"$JOB")"
if [[ -z "$CLIP_PATH" ]]; then
  echo "El job no tiene clips listos." >&2
  exit 1
fi

OUT="$ROOT/data/jobs/$ID/verify-download.mp4"
echo "→ GET $BASE$CLIP_PATH"
curl -fsS "$BASE$CLIP_PATH" -o "$OUT"
python3 - "$OUT" << 'PY'
import json, subprocess, sys
path = sys.argv[1]
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
print(f"{width}x{height} pix_fmt={stream['pix_fmt']} codec={stream['codec_name']}")
if stream["pix_fmt"] != "yuv420p" or stream["codec_name"] != "h264":
    raise SystemExit("El clip no es h264 yuv420p.")
if abs((width / height) - (9 / 16)) > 0.01:
    raise SystemExit(f"El aspecto {width}x{height} no es 9:16.")
print("OK clip vertical 9:16")
PY
