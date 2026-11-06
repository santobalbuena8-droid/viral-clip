# Deploy Viral Clip

Docker image includes Python 3.12, ffmpeg, ffprobe, DejaVu fonts (burned-in subs), and yt-dlp via requirements.

## Env vars

| Var | Default in image | Notes |
| --- | --- | --- |
| `MAX_DURATION_SEC` | `7200` | 2h cap |
| `MOCK_ANALYZE` | `1` | mock clip picker; set `0` + `GEMINI_API_KEY` for real Gemini |
| `DATA_DIR` | `/data` | job scratch |
| `PORT` | platform-injected | uvicorn listens on it |
| `GEMINI_API_KEY` | unset | optional |
| `COOKIES_FILE` | `/etc/secrets/cookies.txt` si ese archivo existe; si no, ninguna | Cookies Netscape de YouTube. No las pongas en git. Ver [PRUEBA-YOUTUBE-RENDER.md](../PRUEBA-YOUTUBE-RENDER.md). |
| `YOUTUBE_PLAYER_CLIENTS` | unset | Lista opcional separada por comas. Vacía: clientes por defecto de yt-dlp. |

## Railway

1. Connect Railway plugin / `railway login`
2. `railway init` / create project
3. Set variables above
4. `railway up` or deploy from GitHub
5. `railway domain` → public HTTPS URL

## Render

1. New Blueprint from `render.yaml` (free web service sleeps after idle)
2. Or Docker web service from repo root Dockerfile
3. Health check `/health`
4. YouTube en la IP del plan free suele pedir el chequeo anti-bot. Cookies opcionales: [PRUEBA-YOUTUBE-RENDER.md](../PRUEBA-YOUTUBE-RENDER.md).

## Fly.io

1. `fly auth login`
2. `fly apps create viral-clip-santo`
3. `fly volumes create viral_clip_data --size 3`
4. `fly deploy`
