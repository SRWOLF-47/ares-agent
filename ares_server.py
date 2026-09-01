import os
import tempfile
import asyncio
import logging
import sqlite3
import json
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

app = FastAPI(title="ARES v4 - Memory")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== CONFIG ======================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VOICE = "es-MX-JorgeNeural"
DB_PATH = "ares_memory.db"          # Se crea automáticamente

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
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

def get_recent_messages(limit: int = 8) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    # Devolver en orden cronológico
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
        except Exception:
            pass

def get_all_facts(limit: int = 25) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT fact FROM facts ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [r["fact"] for r in rows]

def build_memory_context() -> str:
    """Construye el bloque de memoria que se inyecta al prompt."""
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
    """Pide a Gemini que extraiga hechos nuevos sobre el usuario."""
    if not GEMINI_API_KEY:
        return

    extraction_prompt = f"""
Analiza esta conversación y extrae SOLO hechos claros y útiles sobre el usuario (preferencias, proyectos, nombre, gustos, datos personales, estilo de comunicación, etc.).
Devuelve únicamente una lista de hechos, uno por línea. Si no hay hechos nuevos relevantes, devuelve la palabra NADA.

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
    logger.info("Memoria ARES inicializada")


@app.get("/", response_class=HTMLResponse)
async def home():
    # Reutilizamos la misma interfaz visual de v3.1 (bolita + wake word)
    # Por brevedad aquí dejo la llamada; el HTML completo es el de la versión anterior
    # (puedes copiar el HTML de la v3.1 que te di antes)
    return HTMLResponse(content=open("index.html").read() if Path("index.html").exists() else "Interfaz no encontrada. Usa el HTML de la v3.1")


@app.post("/preguntar")
async def preguntar(prompt: str = Form(...)):
    if not prompt.strip():
        raise HTTPException(400, detail="Vacío")

    # 1. Guardar mensaje del usuario
    save_message("user", prompt)

    # 2. Generar respuesta con memoria
    loop = asyncio.get_event_loop()
    texto = await loop.run_in_executor(None, consultar_gemini, prompt)

    # 3. Guardar respuesta de ARES
    save_message("assistant", texto)

    # 4. Extraer hechos nuevos (en segundo plano ligero)
    try:
        extract_and_save_facts(prompt, texto)
    except Exception:
        pass

    # 5. Generar audio
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            temp_path = tmp.name

        ok = await texto_a_voz(texto, temp_path)

        if ok and Path(temp_path).stat().st_size > 800:
            return FileResponse(temp_path, media_type="audio/mpeg", filename="ares.mp3")
        else:
            return JSONResponse({"texto": texto, "error": "TTS falló"})
    except Exception as e:
        logger.error(e)
        return JSONResponse({"texto": texto, "error": str(e)})


@app.get("/memory")
async def ver_memoria():
    """Endpoint de diagnóstico para ver qué recuerda ARES"""
    return {
        "hechos": get_all_facts(30),
        "ultimos_mensajes": get_recent_messages(10)
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "v4-memory",
        "voice": VOICE,
        "api_key": bool(GEMINI_API_KEY),
        "memory_db": DB_PATH
    }
