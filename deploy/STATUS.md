# Viral Clip cloud deploy status (2026-11-06)

## Prepared (on box)
- `/workspace/viral-clip/Dockerfile` — python:3.12-slim + ffmpeg + fonts-dejavu + yt-dlp deps
- `railway.toml`, `render.yaml`, `fly.toml`
- `deploy/README.md`
- Package: `/workspace/viral-clip-deploy.tgz`

## Env intended on host
- `MAX_DURATION_SEC=7200`
- `MOCK_ANALYZE=1` (Gemini optional; leave mock)
- `DATA_DIR=/data`
- `PORT` from platform

## Blockers (cannot finish HTTPS URL without these)
1. No `RAILWAY_TOKEN` / `RENDER_API_KEY` / `FLY_API_TOKEN` in env
2. Executor cannot call `InstallPlugin` (parent must install Railway plugin id `29413143`)
3. Agent email inbox is OFF (cannot sign up for a host that needs a new email)
4. No Vault Railway/Render login visible to this executor (no Vault tool in executor catalog)
5. Docker CLI not installed on the box (image not built here)
6. Local `uvicorn` + `cloudflared` left running as backup (not killed)

## One-click next step for Santo / parent
1. Parent: Install Railway plugin → https://cursor.com/grok-bot/link/v1/plugin/add?id=29413143
2. Santo: Authenticate Railway (OAuth card; trial credit OK)
3. Re-run deploy from `/workspace/viral-clip` (Dockerfile + railway.toml ready)
4. Generate public domain; verify `GET /health` returns `"status":"ok"`
5. Parent rebuilds APK with that HTTPS base URL (no trailing slash)

## Alternate
- Render plugin id `1295` — free tier sleeps after ~15 min idle (worse for phone APK)
