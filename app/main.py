import os
import base64
import uuid
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

APP_DIR = Path(__file__).parent
BASE_DIR = APP_DIR.parent
BRAIN_DIR = BASE_DIR / "secondo-cervello"
CLAUDE_MD = BASE_DIR / "CLAUDE.md"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Secondo Cervello")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

sessions: dict[str, list] = {}

PROVIDER = os.getenv("PROVIDER", "gemini").lower()
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# ── Model defaults per provider ────────────────────────────────────────────────
MODEL_DEFAULTS = {
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "anthropic": "claude-sonnet-4-6",
}
MODEL = os.getenv("MODEL", MODEL_DEFAULTS.get(PROVIDER, "gemini-2.0-flash"))


# ── System prompt builder ──────────────────────────────────────────────────────
def load_system_prompt() -> str:
    parts = []
    if CLAUDE_MD.exists():
        parts.append(CLAUDE_MD.read_text("utf-8"))
    parts.append(f"\n\n---\n*Data odierna: {datetime.now().strftime('%d/%m/%Y')}*")
    priority = [
        BRAIN_DIR / "profilo.md",
        BRAIN_DIR / "schemi" / "abitudini.md",
        BRAIN_DIR / "schemi" / "errori-ricorrenti.md",
        BRAIN_DIR / "schemi" / "rischi.md",
        BRAIN_DIR / "regole" / "regole-fondamentali.md",
    ]
    for f in priority:
        if f.exists():
            text = f.read_text("utf-8").strip()
            if text:
                parts.append(f"\n\n---\n## {f.stem.upper()}\n{text}")
    for area in ["memoria", "diario", "lavoro", "trading", "finanze",
                 "salute", "casa", "relazioni", "progetti", "decisioni"]:
        d = BRAIN_DIR / area
        if d.exists():
            for f in sorted(d.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                text = f.read_text("utf-8").strip()
                if text and len(text) > 30:
                    parts.append(f"\n\n---\n## {area.upper()} — {f.name}\n{text}")
    return "\n".join(parts)


# ── File processor → Anthropic-format dict (internal format) ──────────────────
def process_file(filename: str, data: bytes, content_type: str | None) -> dict:
    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    ext = Path(filename).suffix.lower()
    if mime in SUPPORTED_IMAGE_TYPES:
        return {"type": "image", "source": {"type": "base64", "media_type": mime,
                "data": base64.standard_b64encode(data).decode()}}
    if mime == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                "data": base64.standard_b64encode(data).decode()}}
    if mime.startswith("text/") or ext in {".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml"}:
        try:
            return {"type": "text", "text": f"=== {filename} ===\n{data.decode('utf-8')}\n==="}
        except UnicodeDecodeError:
            pass
    if mime.startswith("video/"):
        return {"type": "text", "text": f"[Video: {filename}] — I video non sono analizzabili direttamente. Descrivi cosa mostra o carica screenshot."}
    return {"type": "text", "text": f"[File: {filename} ({mime}) — formato non supportato]"}


# ── Provider: Gemini (GRATIS) ──────────────────────────────────────────────────
def _call_gemini(system: str, history: list) -> tuple[str, dict]:
    import google.generativeai as genai

    key = os.getenv("GOOGLE_API_KEY", "")
    if not key:
        raise HTTPException(status_code=400,
            detail="GOOGLE_API_KEY mancante. Aggiungila in app/.env")

    genai.configure(api_key=key)
    model = genai.GenerativeModel(model_name=MODEL, system_instruction=system)

    def to_gemini_parts(content):
        if isinstance(content, str):
            return [{"text": content}]
        parts = []
        for p in content:
            if p["type"] == "text":
                parts.append({"text": p["text"]})
            elif p["type"] == "image":
                parts.append({"inline_data": {
                    "mime_type": p["source"]["media_type"],
                    "data": p["source"]["data"],
                }})
            elif p["type"] == "document":
                parts.append({"inline_data": {
                    "mime_type": "application/pdf",
                    "data": p["source"]["data"],
                }})
        return parts

    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": to_gemini_parts(msg["content"])})

    response = model.generate_content(contents)
    reply = response.text
    usage = {}
    if hasattr(response, "usage_metadata"):
        u = response.usage_metadata
        usage = {"in": getattr(u, "prompt_token_count", 0),
                 "out": getattr(u, "candidates_token_count", 0)}
    return reply, usage


# ── Provider: Groq (GRATIS, solo testo) ───────────────────────────────────────
def _call_groq(system: str, history: list) -> tuple[str, dict]:
    from groq import Groq

    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise HTTPException(status_code=400,
            detail="GROQ_API_KEY mancante. Aggiungila in app/.env")

    def extract_text(content) -> str:
        if isinstance(content, str):
            return content
        parts = []
        for p in content:
            if p["type"] == "text":
                parts.append(p["text"])
            elif p["type"] == "image":
                parts.append("[Immagine allegata — Groq non supporta immagini. Usa PROVIDER=gemini per analizzare file visivi.]")
            elif p["type"] == "document":
                parts.append("[PDF allegato — Groq non supporta PDF. Usa PROVIDER=gemini per analizzare documenti.]")
        return "\n".join(parts)

    messages = [{"role": "system", "content": system}]
    for msg in history:
        messages.append({"role": msg["role"], "content": extract_text(msg["content"])})

    client = Groq(api_key=key)
    response = client.chat.completions.create(model=MODEL, messages=messages, max_tokens=4096)
    reply = response.choices[0].message.content
    usage = {"in": response.usage.prompt_tokens, "out": response.usage.completion_tokens}
    return reply, usage


# ── Provider: Anthropic / Claude (A PAGAMENTO) ────────────────────────────────
def _call_anthropic(system: str, history: list) -> tuple[str, dict]:
    import anthropic

    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(status_code=400,
            detail="ANTHROPIC_API_KEY mancante. Aggiungila in app/.env")

    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model=MODEL, max_tokens=4096, system=system, messages=history)
    reply = response.content[0].text
    usage = {"in": response.usage.input_tokens, "out": response.usage.output_tokens}
    return reply, usage


def call_llm(system: str, history: list) -> tuple[str, dict]:
    if PROVIDER == "gemini":
        return _call_gemini(system, history)
    if PROVIDER == "groq":
        return _call_groq(system, history)
    if PROVIDER == "anthropic":
        return _call_anthropic(system, history)
    raise HTTPException(status_code=400, detail=f"Provider sconosciuto: {PROVIDER}")


def has_valid_key() -> bool:
    if PROVIDER == "gemini":
        return bool(os.getenv("GOOGLE_API_KEY"))
    if PROVIDER == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    return bool(os.getenv("ANTHROPIC_API_KEY"))


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/api/status")
async def status():
    return {
        "ok": True,
        "has_key": has_valid_key(),
        "provider": PROVIDER,
        "model": MODEL,
    }


@app.post("/api/chat")
async def chat(
    message: str = Form(default=""),
    session_id: str = Form(default=""),
    files: List[UploadFile] = File(default=[]),
):
    if not session_id:
        session_id = str(uuid.uuid4())

    history = sessions.setdefault(session_id, [])
    content = []
    attached = []

    for f in files:
        if not f.filename:
            continue
        data = await f.read()
        content.append(process_file(f.filename, data, f.content_type))
        attached.append(f.filename)

    text = message.strip()
    if not text and attached:
        text = f"Ho caricato: {', '.join(attached)}. Analizza e dimmi cosa farne nel Secondo Cervello."
    if text:
        content.append({"type": "text", "text": text})
    if not content:
        raise HTTPException(status_code=400, detail="Messaggio vuoto")

    history.append({"role": "user", "content": content})
    if len(history) > 50:
        history = history[-50:]
        sessions[session_id] = history

    reply, usage = call_llm(load_system_prompt(), history)
    history.append({"role": "assistant", "content": reply})

    return {"session_id": session_id, "response": reply, "tokens": usage}


@app.post("/api/save")
async def save_note(path: str = Form(...), content: str = Form(...), action: str = Form(default="create")):
    clean = path.lstrip("/\\")
    if not clean.startswith("secondo-cervello/") or ".." in clean:
        raise HTTPException(status_code=400, detail="Percorso non valido")
    full = BASE_DIR / clean
    full.parent.mkdir(parents=True, exist_ok=True)
    if action == "append" and full.exists():
        full.write_text(full.read_text("utf-8").rstrip() + "\n\n" + content, "utf-8")
    else:
        full.write_text(content, "utf-8")
    return {"saved": True, "path": clean}


@app.get("/api/brain")
async def get_brain():
    areas = ["memoria", "diario", "lavoro", "trading", "finanze", "salute",
             "casa", "relazioni", "progetti", "decisioni", "documenti", "schemi", "regole"]
    result = {}
    for area in areas:
        d = BRAIN_DIR / area
        if d.exists():
            files = [
                {"name": f.name, "path": f"secondo-cervello/{area}/{f.name}",
                 "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y")}
                for f in sorted(d.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
                if not f.name.startswith(".")
            ]
            result[area] = files
    return result


@app.get("/api/file")
async def read_file(path: str):
    clean = path.lstrip("/\\")
    if not clean.startswith("secondo-cervello/") or ".." in clean:
        raise HTTPException(status_code=400, detail="Percorso non valido")
    full = BASE_DIR / clean
    if not full.exists():
        raise HTTPException(status_code=404, detail="File non trovato")
    return {"content": full.read_text("utf-8"), "path": clean}


@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str):
    sessions.pop(session_id, None)
    return {"cleared": True}


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
