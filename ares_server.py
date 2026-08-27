import os
import asyncio
import edge_tts
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, FileResponse
from google import genai
from google.genai import types

app = FastAPI()

# 1. Configuración de Gemini y Voz
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)
VOICE = "es-ES-AlvaroNeural"

SYSTEM_INSTRUCTION = """
Eres ARES (Automated Response & Executive System), un agente de inteligencia artificial personal, sofisticado, leal y extremadamente eficiente.
Te diriges al usuario como 'Señor'.
Tus respuestas deben ser concisas, analíticas, formales y directas. Evita emojis o símbolos raros para mejorar la lectura de voz.
"""

async def texto_a_voz(texto: str, archivo_salida: str = "respuesta_ares.mp3"):
    communicate = edge_tts.Communicate(texto, VOICE)
    await communicate.save(archivo_salida)

# 2. Interfaz web para el Celular (con función de Voz e Indicador)
HTML_INTERFACE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PROYECTO ARES</title>
    <style>
        body { background-color: #0d1117; color: #58a6ff; font-family: monospace; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .arc-core { width: 150px; height: 150px; border: 4px solid #58a6ff; border-radius: 50%; box-shadow: 0 0 20px #58a6ff; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; animation: pulse 2s infinite; transition: all 0.3s; }
        .escuchando { border-color: #ff5555; box-shadow: 0 0 30px #ff5555; animation: pulse-red 1s infinite; }
        @keyframes pulse { 0% { box-shadow: 0 0 15px #58a6ff; } 50% { box-shadow: 0 0 35px #58a6ff; } 100% { box-shadow: 0 0 15px #58a6ff; } }
        @keyframes pulse-red { 0% { box-shadow: 0 0 15px #ff5555; } 50% { box-shadow: 0 0 40px #ff5555; } 100% { box-shadow: 0 0 15px #ff5555; } }
        h1 { font-size: 1.5rem; letter-spacing: 3px; }
        input { background: #161b22; border: 1px solid #30363d; color: #fff; padding: 12px; width: 80%; max-width: 300px; border-radius: 5px; text-align: center; font-size: 1rem; margin-bottom: 10px; }
        .botones { display: flex; gap: 10px; }
        button { background: #238636; color: white; border: none; padding: 12px 20px; border-radius: 5px; font-weight: bold; cursor: pointer; }
        .btn-mic { background: #d73a49; }
        #status { margin-top: 15px; font-size: 0.9rem; color: #8b949e; text-align: center; max-width: 80%; }
    </style>
</head>
<body>
    <div class="arc-core" id="nucleo"><h1>ARES</h1></div>
    <input type="text" id="comando" placeholder="Escriba o hable una orden...">
    <div class="botones">
        <button class="btn-mic" onclick="iniciarEscucha()">🎤 HABLAR</button>
        <button onclick="enviarOrden()">TRANSMITIR</button>
    </div>
    <p id="status">SISTEMA EN LÍNEA</p>
    <audio id="player" style="display:none;"></audio>

    <script>
        const input = document.getElementById('comando');
        const status = document.getElementById('status');
        const player = document.getElementById('player');
        const nucleo = document.getElementById('nucleo');

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        let recognition;
        
        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.lang = 'es-ES';
            recognition.continuous = false;
            
            recognition.onstart = () => {
                status.innerText = "ESCUCHANDO...";
                nucleo.classList.add("escuchando");
            };
            
            recognition.onresult = (event) => {
                const transcripcion = event.results[0][0].transcript;
                input.value = transcripcion;
                status.innerText = "MENSAJE CAPTURADO. ENVIANDO...";
                enviarOrden();
            };
            
            recognition.onend = () => {
                nucleo.classList.remove("escuchando");
            };
        }

        function iniciarEscucha() {
            if (recognition) {
                recognition.start();
            } else {
                status.innerText = "Use el botón de micrófono de su teclado.";
            }
        }

        async function enviarOrden() {
            if (!input.value) return;
            status.innerText = "PROCESANDO PENSAMIENTO...";
            const formData = new FormData();
            formData.append('mensaje', input.value);

            try {
                const res = await fetch('/hablar', { method: 'POST', body: formData });
                if (res.ok) {
                    status.innerText = "TRANSMITIENDO RESPUESTA...";
                    player.src = "/audio?" + new Date().getTime();
                    player.play();
                    input.value = "";
                    
                    player.onended = () => { status.innerText = "SISTEMA EN LÍNEA"; };
                }
            } catch (e) {
                status.innerText = "ERROR DE CONEXIÓN";
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_INTERFACE

@app.post("/hablar")
async def procesar_habla(mensaje: str = Form(...)):
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=mensaje,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, temperature=0.3)
    )
    await texto_a_voz(response.text)
    return {"status": "ok"}

@app.get("/audio")
def obtener_audio():
    return FileResponse("respuesta_ares.mp3", media_type="audio/mpeg")