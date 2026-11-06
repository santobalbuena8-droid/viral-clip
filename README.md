# Viral Clip

Viral Clip convierte un video en clips verticales 9:16. El backend descarga el origen, elige los momentos y FFmpeg los exporta. La app Android **Viral Clip** (`com.viralclip.app`) pega un enlace, sigue el job y reproduce los clips.

Este POC corre en local. Los módulos ya están partidos para servir la API en Cloud Run y mover `run_job` a un worker de Pub/Sub.

## Qué hace

1. `POST /jobs` acepta una URL de YouTube, un `file://` o una ruta local del servidor.
2. yt-dlp baja el video (o se reutiliza el archivo local) si dura como máximo 10 minutos.
3. Gemini Flash elige los intervalos a partir de la transcripción. Sin `GEMINI_API_KEY`, o con `MOCK_ANALYZE=1`, se usan 1–3 ventanas en la parte media del video.
4. FFmpeg recorta al centro, escala a 720×1280 y escribe H.264 `yuv420p`.

Un video de menos de 24 segundos produce un clip. Entre 24 y 42 segundos, como máximo dos. A partir de ahí, hasta tres (o los que pidas, con tope 5 en la API; el modo automático se queda en 3).

## Requisitos

- Python 3.11 o superior
- FFmpeg y ffprobe en el `PATH`
- Para la app: JDK 17 o superior, Android SDK 35 y un dispositivo o emulador

## Backend

```bash
cd /ruta/al/repo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8741
```

Salud:

```bash
curl -sS http://127.0.0.1:8741/health
```

La respuesta trae `"status": "ok"`. La documentación interactiva queda en [http://127.0.0.1:8741/docs](http://127.0.0.1:8741/docs).

El servidor escucha en todas las interfaces para que el emulador y un teléfono en la misma red puedan llegar. Úsalo en una máquina de demo. CORS está abierto para cualquier origen (`Access-Control-Allow-Origin: *`).

## Probar con YouTube

Con el servidor en marcha:

```bash
curl -sS -X POST http://127.0.0.1:8741/jobs \
  -H 'content-type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw","max_clips":1}'
```

Ese enlace es un video público corto («Me at the zoo», unos 19 s). En un servidor o una IP de centro de datos YouTube suele bloquear la descarga con una comprobación anti-bot. El job queda en `failed`, y el recorrido que sí cierra el pipeline es el video local de la sección siguiente. Guarda el `id` y consulta:

```bash
curl -sS http://127.0.0.1:8741/jobs/EL_ID
```

Cuando `status` sea `completed`, descarga un clip:

```bash
curl -sS -o clip.mp4 http://127.0.0.1:8741/jobs/EL_ID/clips/clip-1
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,pix_fmt,codec_name \
  -of default=nw=1 clip.mp4
```

Tiene que salir `720x1280`, `pix_fmt=yuv420p` y `codec_name=h264`.

También puedes lanzarlo en primer plano, sin API:

```bash
python -m app.cli --url "https://www.youtube.com/watch?v=jNQXAC9IVRw" --max-clips 1
```

## Si YouTube no responde

El POC acepta un archivo local. El script genera un MP4 de 60 segundos, 1280×720, con un patrón de prueba y un tono senoidal. No lleva música comercial.

```bash
bash scripts/generate_fixture.sh
# data/fixtures/sample_60s.mp4
```

Por la API, con el servidor ya arrancado (ruta absoluta en la máquina del backend):

```bash
curl -sS -X POST http://127.0.0.1:8741/jobs \
  -H 'content-type: application/json' \
  -d '{"local_path":"/RUTA/ABSOLUTA/data/fixtures/sample_60s.mp4","max_clips":2}'
```

`file://` también vale en el campo `url`:

```bash
curl -sS -X POST http://127.0.0.1:8741/jobs \
  -H 'content-type: application/json' \
  -d '{"url":"file:///RUTA/ABSOLUTA/data/fixtures/sample_60s.mp4","max_clips":2}'
```

El recorrido completo contra la API (fixture, espera, descarga y ffprobe) es:

```bash
bash scripts/demo_api.sh
```

Y el mismo pipeline sin levantar uvicorn:

```bash
bash scripts/demo_local.sh
# equivalente a:
python -m app.cli --local data/fixtures/sample_60s.mp4 --max-clips 2
```

Los artefactos quedan en `data/jobs/<id>/`: `job.json`, el origen, `clips/clip-1.ass` y `clips/clip-1.mp4`. El MP4 lleva los subtítulos quemados.

## Estilo de subtítulos

En Chrome abre [http://127.0.0.1:8741/web.html](http://127.0.0.1:8741/web.html). La sección **Estilo de subtítulos** cambia color del texto, color del contorno, tamaño y fuente. La vista previa es inmediata. El MP4 usa ese estilo en el siguiente «Crear clips».

En la app, el mismo panel está en la pantalla del servidor, encima de **Crear clips**.

Por API, el cuerpo puede incluir `subtitle_style`. Si lo omites, el servidor quema texto blanco, contorno negro, 54 px y Noto Sans:

```bash
curl -sS -X POST http://127.0.0.1:8741/jobs \
  -H 'content-type: application/json' \
  -d '{"local_path":"/RUTA/ABSOLUTA/data/fixtures/sample_60s.mp4","max_clips":1,"subtitle_style":{"text_color":"#FFE14A","outline_color":"#000000","font_size":72,"font_family":"mono"}}'
```

Fuentes del servidor: `sans` Noto Sans, `display` Inter, `serif` Liberation Serif, `mono` Liberation Mono. Si el video no trae subtítulos, se quema el título del clip para que el estilo se vea igual.

## App Android

Nombre visible: **Viral Clip**. Paquete: `com.viralclip.app`.

Pantallas:

- Pegar la URL de YouTube, elegir cuántos clips y crear el job.
- Ver el estado (en cola, descarga, análisis, export, listo o error) y la lista de clips.
- Reproducir cada clip 9:16.
- Cambiar la URL base del backend y probar `/health`.
- Abrir un job que ya exista pegando su id (útil con el fixture local).

Hay un APK debug listo para instalar:

```bash
adb install -r dist/ViralClip-debug.apk
```

### Generar el APK debug

Si prefieres compilarlo tú, el resultado es el mismo paquete `com.viralclip.app`.

Hace falta el Android SDK con `platforms;android-35` y `build-tools;35.0.0`. Android Studio lo instala al abrir el proyecto `android/`. En línea de comandos:

```bash
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(which java)")")")"
export ANDROID_HOME="$HOME/Android/Sdk"   # o la ruta donde esté el SDK
cd android
chmod +x ./gradlew
./gradlew :app:assembleDebug
```

El APK queda en:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

Si Gradle no encuentra el SDK, crea `android/local.properties` (no se versiona):

```properties
sdk.dir=/ruta/absoluta/Android/Sdk
```

### Instalarla y apuntarla al backend

Teléfono por cable, con el servidor en `0.0.0.0:8741`:

```bash
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
adb reverse tcp:8741 tcp:8741
```

En la app pulsa **Cable**. La URL base pasa a `http://127.0.0.1:8741`. Pulsa **Probar conexión** y tiene que decir que está conectado.

En el emulador pulsa **Emulador** (`http://10.0.2.2:8741`). En la misma Wi-Fi escribe `http://IP-DE-TU-ORDENADOR:8741`.

Luego pega un enlace de YouTube y pulsa **Crear clips**. Cuando el estado sea «Listo para ver», **Reproducir 9:16** abre el MP4 que sirve el backend.

El tráfico HTTP en claro está permitido a propósito: el backend de demo no tiene TLS.

## Variables de entorno

| Variable | Por defecto | Efecto |
| --- | --- | --- |
| `GEMINI_API_KEY` | vacía | Sin clave, el análisis es automático |
| `MOCK_ANALYZE` | automático si no hay clave | `1` fuerza las ventanas medias aunque haya clave. `0` exige clave |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo de `google-genai` |
| `MAX_DURATION_SEC` | `600` | Rechaza videos más largos |
| `OUTPUT_WIDTH` / `OUTPUT_HEIGHT` | `720` / `1280` | También vale `1080` / `1920` |
| `DATA_DIR` | `data/` | Carpeta de jobs |

Para usar Gemini de verdad:

```bash
export GEMINI_API_KEY="tu-clave"
export MOCK_ANALYZE=0
```

YouTube tiene que traer subtítulos o subtítulos automáticos. Si no hay transcripción, el job sigue con ventanas medias y lo indica en `analyze_note`. Un archivo local puede acompañarse de un `.vtt` con el mismo nombre al lado.

## API

| Método | Ruta | Cuerpo / respuesta |
| --- | --- | --- |
| `GET` | `/health` | Estado del proceso, FFmpeg y modo de análisis |
| `POST` | `/jobs` | `{"url": "...", "max_clips": 3}` o `{"local_path": "...", "max_clips": 3}`. Responde `202` con el job en `queued` |
| `GET` | `/jobs/{id}` | Job con sus clips, rutas y error si lo hubo |
| `GET` | `/jobs/{id}/clips/{clip_id}` | MP4 cuando el clip está `ready` |

`max_clips` va de 1 a 5. `playback_path` en cada clip listo es la ruta relativa que la app concatena a la URL base, por ejemplo `/jobs/abc123abc123/clips/clip-1`.

## Cómo está partido

```text
app/main.py                 HTTP. Es el servicio que iría a Cloud Run.
app/models.py               Job y Clip (Pydantic).
app/pipeline/download.py    yt-dlp o archivo local.
app/pipeline/analyze.py     Gemini Flash, con ventanas medias de reserva.
app/pipeline/render.py      FFmpeg a 9:16, libx264, yuv420p.
app/pipeline/jobs.py        run_job. Hoy lo llama un BackgroundTask.
android/                    App demo Viral Clip.
data/jobs/<id>/             Origen, job.json y clips.
```

`run_job` no conoce FastAPI. Un push de Pub/Sub puede llamar a la misma función cuando el worker viva aparte. La persistencia de hoy es un JSON por job en disco.

## Límites de este POC

- Duración máxima 10 minutos.
- El modo automático elige ventanas medias; Gemini entra cuando hay clave y transcripción.
- El fixture de prueba es un patrón de vídeo y un seno a 440 Hz.
- Las rutas locales las lee el proceso del servidor. Sirven para la demo en esta máquina.
- Un job a la vez cabe holgado; no hay cola distribuida ni autenticación.

## Si algo falla

- `health` con `"ffmpeg": false`: instala FFmpeg y vuelve a arrancar.
- El job pasa a `failed` con un error de yt-dlp: usa el fixture local de arriba.
- «El video dura …s y el límite de este POC es 600s»: elige un video más corto o sube `MAX_DURATION_SEC`.
- La app dice que no llega al servidor: confirma `uvicorn --host 0.0.0.0 --port 8741`, el preset (Emulador o Cable) y, en un teléfono, `adb reverse tcp:8741 tcp:8741`.
- `MOCK_ANALYZE=0` sin clave: el análisis se detiene con un error explícito. Quita la variable o exporta `GEMINI_API_KEY`.
