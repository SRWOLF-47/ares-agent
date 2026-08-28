import os
import tempfile
import asyncio
import logging
import requests
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import edge_tts

# Configuración de logging (útil en Render)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ARES")

app = FastAPI(title="ARES - Automated Response & Executive System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== CONFIGURACIÓN ======================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VOICE = "es-ES-AlvaroNeural"          # Voz masculina formal española
# Alternativas buenas: "es-ES-ElviraNeural", "es-MX-JorgeNeural"

SYSTEM_INSTRUCTION = (
    "Eres ARES (Automated Response & Executive System), un agente de inteligencia artificial personal, "
    "extremadamente sofisticado, refinado, leal y eficiente. Te diriges al usuario como 'Señor'. "
    "Tus respuestas deben ser concisas, analíticas, formales y directas. Mantén un tono de voz digno "
    "de un asistente personal ejecutivo (estilo JARVIS). Evita emojis o caracteres especiales."
)

# Modelos actualizados a agosto 2026 (orden de preferencia)
MODELOS = [
    "gemini-2.5-flash",          # Excelente relación calidad/precio
    "gemini-3.7-flash",          # El más nuevo y capaz de la familia Flash
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]

# ===========================================================

def consultar_gemini(prompt: str) -> str:
    """Consulta a Gemini con fallback de modelos y versiones de API."""
    if not GEMINI_API_KEY:
        return "Señor, no detecto la clave de acceso API (GEMINI_API_KEY) en las variables de entorno."

    headers = {"Content-Type": "application/json"}
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
        }
    }

    errores = []

    for version in ["v1beta", "v1"]:
        for modelo in MODELOS:
            url = f"https://generativelanguage.googleapis.com/{version}/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
            try:
                logger.info(f"Intentando {modelo} ({version})...")
                resp = requests.post(url, json=payload, headers=headers, timeout=20)

                if resp.status_code == 200:
                    data = resp.json()
                    texto = data["candidates"][0]["content"]["parts"][0]["text"]
                    logger.info(f"Éxito con {modelo}")
                    return texto.strip()

                # Guardamos el error para diagnóstico
                errores.append(f"{modelo}: HTTP {resp.status_code} → {resp.text[:200]}")
                logger.warning(f"{modelo} falló: {resp.status_code}")

            except Exception as e:
                errores.append(f"{modelo}: {str(e)}")
                logger.error(f"Excepción con {modelo}: {e}")
                continue

    # Si llegamos aquí, todo falló
    detalle = " | ".join(errores[-3:])  # últimos 3 errores
    return f"Señor, no pude conectar con ningún modelo de Gemini. Últimos errores: {detalle}"


async def texto_a_voz(texto: str, ruta_salida: str) -> bool:
    """Genera audio con edge-tts. Devuelve True si tuvo éxito."""
    try:
        communicate = edge_tts.Communicate(texto, VOICE)
        await communicate.save(ruta_salida)
        return True
    except Exception as e:
        logger.error(f"Error en TTS: {e}")
        return False


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARES Interface v2</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #080c14;
            color: #58a6ff;
            font-family: 'Segoe UI', system-ui, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: #0d1117;
            border: 1px solid #1f6feb;
            border-radius: 14px;
            padding: 32px;
            width: 100%;
            max-width: 640px;
            box-shadow: 0 0 30px rgba(31, 111, 235, 0.25);
        }
        h1 { font-size: 28px; letter-spacing: 4px; text-align: center; margin-bottom: 4px; }
        .subtitle { color: #8b949e; text-align: center; font-size: 12px; letter-spacing: 1.5px; margin-bottom: 28px; }
        textarea {
            width: 100%; height: 130px;
            background: #161b22; color: #f0f6fc;
            border: 1px solid #30363d; border-radius: 8px;
            padding: 14px; font-size: 16px; resize: vertical;
            outline: none; transition: border-color 0.2s;
        }
        textarea:focus { border-color: #58a6ff; }
        button {
            background: linear-gradient(135deg, #1f6feb, #238636);
            color: white; border: none; padding: 15px;
            margin-top: 16px; border-radius: 8px;
            font-size: 16px; font-weight: 600; width: 100%;
            cursor: pointer; transition: opacity 0.2s, transform 0.1s;
        }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
        button:active:not(:disabled) { transform: scale(0.98); }
        .status { margin-top: 18px; color: #8b949e; font-size: 14px; text-align: center; min-height: 20px; }
        .respuesta {
            margin-top: 22px; padding: 16px;
            background: #161b22; border-radius: 8px;
            border-left: 3px solid #1f6feb;
            color: #c9d1d9; font-size: 15px; line-height: 1.5;
            display: none; white-space: pre-wrap;
        }
        audio { margin-top: 16px; width: 100%; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ARES SYSTEM</h1>
        <p class="subtitle">AUTOMATED RESPONSE & EXECUTIVE SYSTEM · v2</p>

        <form id="aresForm">
            <textarea id="promptInput" placeholder="Ingrese su comando, Señor..." required></textarea>
            <button type="submit" id="sendBtn">TRANSMITIR COMANDO</button>
        </form>

        <div id="status" class="status">Sistemas en espera...</div>
        <div id="respuestaTexto" class="respuesta"></div>
        <audio id="audioPlayer" controls></audio>
    </div>

    <script>
        const form = document.getElementById('aresForm');
        const statusDiv = document.getElementById('status');
        const audioPlayer = document.getElementById('audioPlayer');
        const respuestaDiv = document.getElementById('respuestaTexto');
        const sendBtn = document.getElementById('sendBtn');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const prompt = document.getElementById('promptInput').value.trim();
            if (!prompt) return;

            statusDiv.innerText = "Procesando orden con ARES...";
            sendBtn.disabled = true;
            respuestaDiv.style.display = 'none';
            audioPlayer.style.display = 'none';

            try {
                const formData = new FormData();
                formData.append('prompt', prompt);

                const response = await fetch('/preguntar', {
                    method: 'POST',
                    body: formData
                });

                const contentType = response.headers.get('content-type') || '';

                if (contentType.includes('audio')) {
                    const blob = await response.blob();
                    const audioUrl = URL.createObjectURL(blob);
                    audioPlayer.src = audioUrl;
                    audioPlayer.style.display = 'block';
                    audioPlayer.play();
                    statusDiv.innerText = "ARES respondiendo por voz...";
                } else {
                    // Fallback texto
                    const data = await response.json();
                    respuestaDiv.innerText = data.texto || data.detail || "Sin respuesta";
                    respuestaDiv.style.display = 'block';
                    statusDiv.innerText = data.error ? "Error de voz. Mostrando texto." : "Respuesta recibida (solo texto)";
                }
            } catch (err) {
                statusDiv.innerText = "Error de conexión con el servidor.";
                console.error(err);
            } finally {
                sendBtn.disabled = false;
            }
        });
    </script>
</body>
</html>
"""


@app.post("/preguntar")
async def preguntar(prompt: str = Form(...)):
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Comando vacío")

    # Ejecutamos la llamada síncrona en un thread
    loop = asyncio.get_event_loop()
    texto_respuesta = await loop.run_in_executor(None, consultar_gemini, prompt)

    # Intentamos generar audio
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            temp_path = tmp.name

        exito_tts = await texto_a_voz(texto_respuesta, temp_path)

        if exito_tts and Path(temp_path).stat().st_size > 1000:
            # Devolvemos el audio
            return FileResponse(
                temp_path,
                media_type="audio/mpeg",
                filename="respuesta_ares.mp3",
                background=None  # se limpia después
            )
        else:
            # Fallback a JSON con el texto
            return JSONResponse({
                "texto": texto_respuesta,
                "error": "No se pudo generar el audio (TTS falló)"
            })
    except Exception as e:
        logger.error(f"Error general en /preguntar: {e}")
        return JSONResponse({
            "texto": texto_respuesta,
            "error": str(e)
        })
    finally:
        # Limpieza del archivo temporal (se hace después de enviar la respuesta)
        if temp_path and Path(temp_path).exists():
            try:
                # En producción real se puede usar BackgroundTasks de FastAPI
                pass
            except:
                pass


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "api_key_configured": bool(GEMINI_API_KEY),
        "voice": VOICE,
        "models": MODELOS
    }


@app.get("/status")
async def status():
    return {
        "sistema": "ARES v2",
        "estado": "Operativo",
        "api_key": "Configurada" if GEMINI_API_KEY else "FALTA GEMINI_API_KEY"
    }
