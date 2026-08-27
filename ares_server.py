import os
import tempfile
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
        <title>ARES Agent</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #0d1117; color: #c9d1d9; text-align: center; padding: 20px; }
            h1 { color: #58a6ff; }
            textarea { width: 90%; max-width: 500px; height: 100px; background: #161b22; color: #fff; border: 1px solid #30363d; border-radius: 8px; padding: 10px; font-size: 16px; }
            button { background: #238636; color: white; border: none; padding: 12px 24px; margin-top: 10px; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; }
            button:hover { background: #2ea043; }
        </style>
    </head>
    <body>
        <h1>ARES System Online</h1>
        <form action="/preguntar" method="post">
            <textarea name="prompt" placeholder="Escriba su comando, Señor..."></textarea><br>
            <button type="submit">Enviar a ARES</button>
        </form>
    </body>
    </html>
    """
    return html_content

@app.post("/preguntar")
async def preguntar(prompt: str = Form(...)):
    # Usamos modelo oficial de producción de Gemini
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )
    
    texto_respuesta = response.text if response.text else "Entendido, Señor."
    
    # Crear archivo temporal seguro para el servidor en la nube
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    ruta_audio = temp_file.name
    temp_file.close()

    # Generar audio
    await texto_a_voz(texto_respuesta, ruta_audio)
    
    return FileResponse(ruta_audio, media_type="audio/mpeg", filename="respuesta_ares.mp3")
