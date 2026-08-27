import os
import tempfile
import asyncio
import edge_tts
import google.generativeai as genai
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, FileResponse

app = FastAPI()

# 1. Configuración de Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Voz estilo JARVIS (Elegante, formal y ejecutiva)
VOICE = "es-ES-AlvaroNeural"

SYSTEM_INSTRUCTION = """
Eres ARES (Automated Response & Executive System), un agente de inteligencia artificial personal, extremadamente sofisticado, refinado, leal y eficiente.
Te diriges al usuario como 'Señor'.
Tus respuestas deben ser concisas, analíticas, formales y directas. 
Mantén un tono de voz digno de un asistente personal ejecutivo (estilo JARVIS).
Evita emojis o caracteres especiales para garantizar una síntesis de voz perfecta.
"""

async def texto_a_voz(texto: str, ruta_salida: str):
    # Ajustamos ligeramente la velocidad para darle más elegancia al hablar
    communicate = edge_tts.Communicate(texto, VOICE, rate="-5%")
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
            .status { margin-top: 20px; color: #8b949e; font-size: 14px; display: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>ARES SYSTEM</h1>
            <p class="subtitle">AUTOMATED RESPONSE & EXECUTIVE SYSTEM</p>
            <form action="/preguntar" method="post" onsubmit="document.getElementById('status').style.display='block';">
                <textarea name="prompt" placeholder="Ingrese su comando, Señor..." required></textarea>
                <button type="submit">TRANSMITIR COMANDO</button>
            </form>
            <div id="status" class="status">Procesando orden en los servidores...</div>
        </div>
    </body>
    </html>
    """
    return html_content

@app.post("/preguntar")
async def preguntar(prompt: str = Form(...)):
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_INSTRUCTION
    )
    
    response = model.generate_content(prompt)
    texto_respuesta = response.text if response.text else "A su servicio, Señor."
    
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    ruta_audio = temp_file.name
    temp_file.close()

    await texto_a_voz(texto_respuesta, ruta_audio)
    
    return FileResponse(ruta_audio, media_type="audio/mpeg", filename="respuesta_ares.mp3")
