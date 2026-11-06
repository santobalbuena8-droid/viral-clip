# Viral Clip — servidor en casa (LAN)

Corre Viral Clip en tu PC. El celular y Chrome usan la misma Wi‑Fi y hablan con `http://TU_IP:8741`. **Gratis**: no hace falta nube de pago.

## Requisitos

- Python 3.10+ **o** Docker
- FFmpeg en el PATH (si usas Python; con Docker ya viene)
- Misma red Wi‑Fi entre PC y celular

## Opción A — Python (Windows / Linux / Mac)

1. Abre una terminal en la carpeta del proyecto (`viral-clip`, la que tiene `app/` y `requirements.txt`).
2. Instala dependencias (una sola vez):

```bash
python -m venv .venv
```

Windows (cmd):

```bat
.venv\Scripts\activate
pip install -r requirements.txt
```

Linux / Mac:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

3. Instala FFmpeg si no lo tienes:
   - Windows: [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html) o `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`

4. Arranca el servidor:

Windows — doble clic o:

```bat
home-server\start.bat
```

Linux / Mac:

```bash
chmod +x home-server/start.sh
./home-server/start.sh
```

Deja esa ventana abierta mientras uses la app.

## Opción B — Docker

En la carpeta del proyecto:

```bash
docker compose -f home-server/docker-compose.yml up --build
```

## Averiguar la IP de tu PC (en casa)

**Windows** — cmd o PowerShell:

```bat
ipconfig
```

Busca **IPv4** de tu Wi‑Fi / Ethernet (suele ser `192.168.x.x` o `10.x.x.x`).

**Mac / Linux:**

```bash
ifconfig
```

o:

```bash
ip addr
```

Misma idea: la IP de la interfaz Wi‑Fi/LAN, no `127.0.0.1`.

## Firewall (importante)

La primera vez Windows puede preguntar: permite **redes privadas**. Si no conecta el celular:

```bat
netsh advfirewall firewall add rule name="Viral Clip 8741" dir=in action=allow protocol=TCP localport=8741
```

Linux (ufw):

```bash
sudo ufw allow 8741/tcp
```

## En el celular (APK Viral Clip)

1. Abre la app → sección **SERVIDOR**
2. Pega: `http://TU_IP:8741`  
   Ejemplo: `http://192.168.1.42:8741`
3. Toca **Probar conexión** → debe decir Conectado
4. Pega el enlace de YouTube → **Crear clips**
5. Cuando termine, **Descargar MP4** en cada clip

Chrome en el celular o en la PC: abre la misma URL `http://TU_IP:8741`.

## Fuera de casa (opcional)

Si no estás en la misma Wi‑Fi, el servidor de casa no se alcanza. Opciones:

- Encender el PC en casa + túnel (Cloudflare / Grok Bot egress) y pegar esa URL HTTPS en SERVIDOR
- O usar solo cuando estés en casa (recomendado y gratis)

## Notas

- Puerto fijo: **8741**
- Videos largos: hasta ~2 horas (`MAX_DURATION_SEC=7200`)
- Los clips salen con subtítulos quemados cuando hay texto disponible
- No cierres la terminal del servidor mientras generas clips
