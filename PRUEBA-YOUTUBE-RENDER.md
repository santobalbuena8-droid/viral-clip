# Probar YouTube en Render (cookies)

En las IP de datacenter del plan free de Render, yt-dlp suele fallar con
«Sign in to confirm you're not a bot». Este servicio ya no fuerza los
clientes `android` y `web`. Si no defines `YOUTUBE_PLAYER_CLIENTS`, yt-dlp
usa sus clientes por defecto.

Un archivo de cookies en formato Netscape **puede** ayudar. No garantiza
la descarga: una IP que YouTube ya bloqueó puede seguir fallando. Un PO
token no desbloquea esa IP; no lo configures esperando saltarte el bloqueo.

## Riesgo de la cuenta

Pasar cookies de una sesión iniciada puede hacer que YouTube restrinja o
cierre esa cuenta. Los maintainers de yt-dlp lo advierten. No uses tu
cuenta principal. Si aceptas el riesgo, usa una cuenta secundaria que
puedas perder. Exportar cookies de YouTube también puede ir contra las
condiciones del servicio.

## Exportar cookies (Netscape)

1. En Chrome o Firefox, entra en [youtube.com](https://www.youtube.com) con esa cuenta secundaria.
2. Instala una extensión que exporte cookies **en tu máquina**, sin subirlas a otro servidor. La wiki de yt-dlp recomienda «Get cookies.txt LOCALLY».
3. En youtube.com, exporta las cookies. Si la extensión pregunta el formato, elige Netscape.
4. El archivo es texto. La primera línea suele ser `# Netscape HTTP Cookie File`, y las siguientes son de `.youtube.com`.

No pegues ese archivo en el chat, en un issue, en `render.yaml` ni en el repo.

## Subirlas al servicio `viral-clip`

1. Render → servicio **viral-clip** → **Environment** → **Secret Files**.
2. Nombre del archivo: `cookies.txt`. Render lo monta en `/etc/secrets/cookies.txt`.
3. Pega el contenido exportado y guarda.
4. Variable opcional `COOKIES_FILE` = `/etc/secrets/cookies.txt`. Si no la pones y ese archivo existe, la app lo usa sola. Si `COOKIES_FILE` apunta a otra ruta, se usa esa y no el default.
5. Opcional: `YOUTUBE_PLAYER_CLIENTS` con clientes separados por comas, por ejemplo `web,tv_embedded`. Déjala vacía para no forzar `player_client`.
6. Guarda y espera el **redeploy**. Un Secret File nuevo no entra en el contenedor que ya está corriendo.

La app solo registra la ruta del archivo, nunca el contenido.

## Probar «Me at the zoo»

Video público y corto: <https://www.youtube.com/watch?v=jNQXAC9IVRw>

En la web del servicio, pega el enlace y toca **Crear clips**. O, con la URL pública del servicio:

```bash
curl -sS -X POST "$URL/jobs" \
  -H 'content-type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw","max_clips":1}'
```

Consulta `GET /jobs/EL_ID`. Si `status` llega a `completed`, la descarga pasó. Si el error sigue hablando de bot, la IP puede seguir bloqueada aunque haya cookies. Entonces:

- toca **Probar con video de muestra** (no usa YouTube), o
- corre el servidor en un PC de casa, donde YouTube suele aceptar la petición sin cookies.

## Qué no hacer

- No hagas commit de `cookies.txt`. Está en `.gitignore`; no lo quites para subirlo.
- No pegues las cookies en git, en issues ni en variables normales del Blueprint (usa Secret File).
- No cuentes con que YouTube ya funciona en Render sin cookies.
