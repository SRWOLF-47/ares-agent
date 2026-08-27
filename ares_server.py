import os
import tempfile
import asyncio
import requests
import edge_tts
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, FileResponse

app = FastAPI()

# 1. Configuración de API Key y Voz
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VOICE = "es-ES-AlvaroNeural"

SYSTEM_INSTRUCTION = (
    "Eres ARES (Automated Response & Executive System), un agente de inteligencia artificial personal, "
    "extremadamente sofisticado, refinado, leal y eficiente. Te diriges al usuario como 'Señor'. "
    "Tus respuestas deben ser concisas, analíticas, formales y directas. Mantén un tono de voz digno "
    "de un asistente personal ejecutivo (estilo JARVIS). Evita emojis o caracteres especiales."
)

# Lista de modelos a intentar en orden de preferencia
MODELOS_TENTATIVOS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-pro"
]

def consultar_gemini(prompt: str) -> str:
    """Consulta directa a la API oficial de Gemini probando versiones v1beta y v1 automáticamente."""
    if not GEMINI_API_KEY:
        return "Señor, no detecto la clave de acceso API en las variables de entorno de Render."

    headers = {"Content-Type": "application/json"}
    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }

    # Recorremos los modelos y versiones de API hasta que uno funcione
    for version_api in ["v1beta", "v1"]:
        for modelo in MODELOS_TENTATIVOS:
            url = f"https://generativelanguage.googleapis.com/{version_api}/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=12)
                if response.status_code == 200:
                    data = response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                continue

    return "Señor, no fue posible conectar con los modelos de Gemini. Verifique la validez de su API Key."

async def texto_a_voz(texto: str, ruta_salida: str):
    communicate = edge_tts.Communicate(texto, VOICE)
    await communicate.save(ruta_salida)

@app.get("/", response_class=HTMLResponse)
async def home():
    html_content = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ARES Interface</title>
        <style>
            * { box-sizing: border-box; }
            body { 
                background-color: #080c14; 
                color: #58a6ff; 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                display: flex; 
                flex-direction: column; 
                align-items: center; 
                justify-content: center; 
                min-height: 100vh; 
                margin: 0; 
                padding: 20px;
            }
            .container {
                background: #0d1117;
                border: 1px solid #1f6feb;
                border-radius: 12px;
                padding: 30px;
                width: 100%;
                max-width: 600px;
                box-shadow: 0 0 25px rgba(31, 111, 235, 0.25);
                text-align: center;
            }
            h1 { margin-bottom: 5px; font-size: 28px; letter-spacing: 3px; }
            p.subtitle { color: #8b949e; margin-bottom: 25px; font-size: 13px; letter-spacing: 1px; }
            textarea { 
                width: 100%; 
                height: 120px; 
                background: #161b22; 
                color: #f0f6fc; 
                border: 1px solid #30363d; 
                border-radius: 8px; 
                padding: 12px; 
                font-size: 16px; 
                resize: none; 
                outline: none;
            }
            textarea:focus { border-color: #58a6ff; }
            button { 
                background: linear-gradient(135deg, #1f6feb, #238636); 
                color: white; 
                border: none; 
                padding: 14px 28px; 
                margin-top: 15px; 
                border-radius: 8px; 
                cursor: pointer; 
                font-size: 16px; 
                font-weight: bold; 
                width: 100%;
                transition: transform 0.2s, opacity 0.2s;
            }
            button:active { transform: scale(0.98); }
            .status { margin-top: 20px; color: #8b949e; font-size: 14px; }
            audio { margin-top: 20px; width: 100%; display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>ARES SYSTEM</h1>
            <p class="subtitle">AUTOMATED RESPONSE & EXECUTIVE SYSTEM</p>
            <form id="aresForm">
                <textarea id="promptInput" name="prompt" placeholder="Ingrese su comando, Señor..." required></textarea>
                <button type="submit" id="sendBtn">TRANSMITIR COMANDO</button>
            </form>
            <div id="status" class="status">Sistemas en espera...</div>
            <audio id="audioPlayer" controls></audio>
        </div>

        <script>
            const form = document.getElementById('aresForm');
            const statusDiv = document.getElementById('status');
            const audioPlayer = document.getElementById('audioPlayer');
            const sendBtn = document.getElementById('sendBtn');

            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const prompt = document.getElementById('promptInput').value;
                
                statusDiv.innerText = "Procesando orden con ARES...";
                sendBtn.disabled = true;

                try {
                    const formData = new FormData();
                    formData.append('prompt', prompt);

                    const response = await fetch('/preguntar', {
                        method: 'POST',
                        body: formData
                    });

                    if (!response.ok) throw new Error("Error en la transmisión");

                    const blob = await response.blob();
                    const audioUrl = URL.createObjectURL(blob);
                    
                    audioPlayer.src = audioUrl;
                    audioPlayer.style.display = 'block';
                    audioPlayer.play();
                    
                    statusDiv.innerText = "ARES respondiendo...";
                } catch (err) {
                    statusDiv.innerText = "Error al conectar con el servidor.";
                } finally {
                    sendBtn.disabled = false;
                }
            });
        </script>
    </body>
    </html>
    """
    return html_content

@app.post("/preguntar")
async def preguntar(prompt: str = Form(...)):
    loop = asyncio.get_event_loop()
    texto_respuesta = await loop.run_in_executor(None, consultar_gemini, prompt)

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    ruta_audio = temp_file.name
    temp_file.close()

    await texto_a_voz(texto_respuesta, ruta_audio)
    
    return FileResponse(ruta_audio, media_type="audio/mpeg", filename="respuesta_ares.mp3")
