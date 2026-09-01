import os
import tempfile
import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import edge_tts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ARES-v4")

app = FastAPI(title="ARES v4 - Memory + Wake Word")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== CONFIG ======================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VOICE = "es-MX-JorgeNeural"
DB_PATH = "ares_memory.db"

SYSTEM_BASE = (
    "Eres ARES, un asistente ejecutivo de inteligencia artificial de élite. "
    "Te diriges al usuario como 'Señor'. "
    "Responde siempre de forma extremadamente concisa, directa, formal y analítica. "
    "Máximo 3-4 frases cortas. Nunca uses emojis ni caracteres especiales. "
    "Tono digno de un mayordomo ejecutivo de alto nivel (estilo JARVIS)."
)

MODELOS = [
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.7-flash",
]

# ====================================================
#                    MEMORIA
# ====================================================

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL UNIQUE,
                category TEXT DEFAULT 'general',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def save_message(role: str, content: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
            (role, content, datetime.utcnow().isoformat())
        )

def get_recent_messages(limit: int = 8):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def save_fact(fact: str, category: str = "general"):
    fact = fact.strip()
    if len(fact) < 8:
        return
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO facts (fact, category, created_at) VALUES (?, ?, ?)",
                (fact, category, datetime.utcnow().isoformat())
            )
        except:
            pass

def get_all_facts(limit: int = 25):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT fact FROM facts ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [r["fact"] for r in rows]

def build_memory_context() -> str:
    facts = get_all_facts(20)
    recent = get_recent_messages(6)
    parts = []
    if facts:
        parts.append("### Hechos importantes que conoces sobre el usuario:")
        for f in facts:
            parts.append(f"- {f}")
    if recent:
        parts.append("\n### Conversación reciente:")
        for msg in recent:
            role = "Usuario" if msg["role"] == "user" else "ARES"
            parts.append(f"{role}: {msg['content']}")
    return "\n".join(parts) if parts else ""

def extract_and_save_facts(user_text: str, ares_text: str):
    if not GEMINI_API_KEY:
        return
    extraction_prompt = f"""
Analiza esta conversación y extrae SOLO hechos claros y útiles sobre el usuario.
Devuelve únicamente una lista de hechos, uno por línea. Si no hay hechos nuevos, devuelve la palabra NADA.

Usuario: {user_text}
ARES: {ares_text}
"""
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": extraction_prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300}
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code == 200:
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text.upper() != "NADA":
                for line in text.split("\n"):
                    line = line.strip("-•* ").strip()
                    if line:
                        save_fact(line)
    except Exception as e:
        logger.warning(f"Error extrayendo hechos: {e}")

# ====================================================
#                 GEMINI + TTS
# ====================================================

def consultar_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return "Señor, no detecto la clave GEMINI_API_KEY."

    memory = build_memory_context()
    full_system = SYSTEM_BASE
    if memory:
        full_system += "\n\n" + memory + "\n\nUsa esta información para personalizar tus respuestas cuando sea relevante."

    headers = {"Content-Type": "application/json"}
    payload = {
        "system_instruction": {"parts": [{"text": full_system}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.55,
            "maxOutputTokens": 320,
        }
    }

    for version in ["v1beta", "v1"]:
        for modelo in MODELOS:
            url = f"https://generativelanguage.googleapis.com/{version}/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                logger.warning(f"{modelo} falló: {e}")
                continue

    return "Señor, no pude conectar con los modelos de Gemini."

async def texto_a_voz(texto: str, ruta: str) -> bool:
    try:
        communicate = edge_tts.Communicate(texto, VOICE, rate="-8%", pitch="-3Hz")
        await communicate.save(ruta)
        return True
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return False

# ====================================================
#                     RUTAS
# ====================================================

@app.on_event("startup")
def startup():
    init_db()
    logger.info("ARES v4 con memoria iniciado")

@app.get("/", response_class=HTMLResponse)
async def home():
    html = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <title>ARES v4</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #05050a;
            color: #e0d4ff;
            font-family: 'Segoe UI', system-ui, sans-serif;
            height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            user-select: none;
        }
        .title {
            position: absolute;
            top: 36px;
            letter-spacing: 8px;
            font-size: 13px;
            color: #9b7bff;
            opacity: 0.7;
        }
        .orb-container {
            position: relative;
            width: 240px;
            height: 240px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }
        .orb {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            background: radial-gradient(circle at 35% 35%,
                #d4a5ff 0%, #9b4dff 35%, #5c1db8 70%, #2a0a5e 100%);
            box-shadow: 0 0 40px rgba(155, 77, 255, 0.55),
                        0 0 80px rgba(120, 40, 220, 0.3),
                        inset 0 0 30px rgba(255,255,255,0.12);
            position: relative;
            z-index: 10;
        }
        .ring {
            position: absolute;
            border-radius: 50%;
            border: 2px solid rgba(180, 100, 255, 0.35);
            opacity: 0;
        }
        .ring1 { width: 150px; height: 150px; }
        .ring2 { width: 190px; height: 190px; }
        .ring3 { width: 230px; height: 230px; }

        .idle .orb { animation: breathe 3.8s ease-in-out infinite; }
        .wake .orb {
            animation: pulse-wake 1.3s ease-in-out infinite;
            box-shadow: 0 0 55px rgba(180, 90, 255, 0.85), 0 0 110px rgba(140, 50, 255, 0.45);
        }
        .listening .orb {
            animation: pulse-listen 1.0s ease-in-out infinite;
            box-shadow: 0 0 70px rgba(200, 100, 255, 0.95), 0 0 130px rgba(160, 60, 255, 0.55);
        }
        .listening .ring { animation: expand 1.3s ease-out infinite; }
        .listening .ring2 { animation-delay: 0.22s; }
        .listening .ring3 { animation-delay: 0.44s; }
        .thinking .orb { animation: spin-glow 1.7s linear infinite; }
        .speaking .orb {
            animation: speak-pulse 0.65s ease-in-out infinite;
            box-shadow: 0 0 75px rgba(210, 130, 255, 1), 0 0 150px rgba(170, 70, 255, 0.65);
        }

        @keyframes breathe {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        @keyframes pulse-wake {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.08); }
        }
        @keyframes pulse-listen {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.13); }
        }
        @keyframes expand {
            0% { transform: scale(0.65); opacity: 0.65; }
            100% { transform: scale(1.45); opacity: 0; }
        }
        @keyframes spin-glow {
            0% { transform: rotate(0deg) scale(1); }
            50% { transform: rotate(180deg) scale(1.07); }
            100% { transform: rotate(360deg) scale(1); }
        }
        @keyframes speak-pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.14); }
        }

        .status {
            margin-top: 48px;
            font-size: 15px;
            color: #b89cff;
            letter-spacing: 0.8px;
            min-height: 24px;
            text-align: center;
            opacity: 0.9;
            max-width: 320px;
            line-height: 1.4;
        }
        .hint {
            position: absolute;
            bottom: 36px;
            font-size: 12.5px;
            color: #6b5b9a;
            text-align: center;
            max-width: 300px;
            line-height: 1.45;
        }
        audio { display: none; }
    </style>
</head>
<body>
    <div class="title">A R E S &nbsp; v 4</div>

    <div class="orb-container idle" id="orbContainer">
        <div class="ring ring1"></div>
        <div class="ring ring2"></div>
        <div class="ring ring3"></div>
        <div class="orb" id="orb"></div>
    </div>

    <div class="status" id="status">Di "Hey Ares" o "Oye Ares"</div>
    <div class="hint">
        Activa el micrófono la primera vez.<br>
        Palabras clave: Hey Ares · Oye Ares · Ok Ares · Ares
    </div>

    <audio id="player"></audio>

    <script>
        const orbContainer = document.getElementById('orbContainer');
        const statusEl = document.getElementById('status');
        const player = document.getElementById('player');

        const WAKE_PHRASES = [
            "hey ares", "oye ares", "ok ares", "okay ares",
            "hola ares", "ares", "ei ares", "ey ares"
        ];

        let recognition = null;
        let mode = "wake";
        let isProcessing = false;
        let restartTimeout = null;

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            statusEl.textContent = "Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.";
        } else {
            initRecognition();
            startWakeListening();
        }

        function initRecognition() {
            recognition = new SpeechRecognition();
            recognition.lang = "es-MX";
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.maxAlternatives = 1;

            recognition.onresult = (event) => {
                let transcript = "";
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    transcript += event.results[i][0].transcript;
                }
                transcript = transcript.toLowerCase().trim();

                if (mode === "wake") {
                    const detected = WAKE_PHRASES.some(phrase => transcript.includes(phrase));
                    if (detected) {
                        onWakeWord();
                    }
                } else if (mode === "command") {
                    if (event.results[event.results.length - 1].isFinal) {
                        const finalText = event.results[event.results.length - 1][0].transcript.trim();
                        if (finalText.length > 1) {
                            recognition.stop();
                            processCommand(finalText);
                        }
                    }
                }
            };

            recognition.onerror = (e) => {
                if (e.error === "not-allowed") {
                    statusEl.textContent = "Permiso de micrófono denegado";
                    return;
                }
                scheduleRestart();
            };

            recognition.onend = () => {
                if (!isProcessing) scheduleRestart();
            };
        }

        function scheduleRestart() {
            clearTimeout(restartTimeout);
            restartTimeout = setTimeout(() => {
                if (!isProcessing && mode === "wake") {
                    startWakeListening();
                }
            }, 350);
        }

        function startWakeListening() {
            mode = "wake";
            setState("idle");
            statusEl.textContent = 'Di "Hey Ares" o "Oye Ares"';
            try { recognition.start(); } catch (e) {}
        }

        function onWakeWord() {
            mode = "command";
            recognition.stop();
            setState("wake");
            statusEl.textContent = "Sí, Señor...";

            setTimeout(() => {
                setState("listening");
                statusEl.textContent = "Te escucho...";
                recognition.continuous = false;
                recognition.interimResults = false;
                try { recognition.start(); } catch (e) {}
            }, 600);
        }

        async function processCommand(texto) {
            isProcessing = true;
            setState("thinking");
            statusEl.textContent = '"' + texto + '"';

            recognition.continuous = true;
            recognition.interimResults = true;

            try {
                const formData = new FormData();
                formData.append("prompt", texto);

                const response = await fetch("/preguntar", {
                    method: "POST",
                    body: formData
                });

                if (!response.ok) throw new Error("Error servidor");

                const contentType = response.headers.get("content-type") || "";

                if (contentType.includes("audio")) {
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    player.src = url;
                    setState("speaking");
                    statusEl.textContent = "ARES respondiendo...";

                    player.onended = () => {
                        URL.revokeObjectURL(url);
                        isProcessing = false;
                        startWakeListening();
                    };
                    await player.play();
                } else {
                    const data = await response.json();
                    statusEl.textContent = data.texto || "Sin audio";
                    isProcessing = false;
                    startWakeListening();
                }
            } catch (err) {
                console.error(err);
                statusEl.textContent = "Error de conexión";
                isProcessing = false;
                startWakeListening();
            }
        }

        function setState(state) {
            orbContainer.className = "orb-container " + state;
        }

        orbContainer.addEventListener("click", () => {
            if (isProcessing) return;
            if (mode === "wake") onWakeWord();
        });
    </script>
</body>
</html>
'''
    return HTMLResponse(content=html)
