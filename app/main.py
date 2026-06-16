import os
import base64
import uuid
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import anthropic

load_dotenv()

APP_DIR = Path(__file__).parent
BASE_DIR = APP_DIR.parent
BRAIN_DIR = BASE_DIR / "secondo-cervello"
CLAUDE_MD = BASE_DIR / "CLAUDE.md"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Secondo Cervello")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

sessions: dict[str, list] = {}
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def get_client() -> anthropic.Anthropic:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise HTTPException(
            status_code=400,
            detail="API key mancante. Crea il file app/.env con ANTHROPIC_API_KEY=sk-ant-..."
        )
    return anthropic.Anthropic(api_key=key)


def load_system_prompt() -> str:
    parts = []

    if CLAUDE_MD.exists():
        parts.append(CLAUDE_MD.read_text("utf-8"))

    parts.append(f"\n\n---\n*Data odierna: {datetime.now().strftime('%d/%m/%Y')}*")

    priority_files = [
        BRAIN_DIR / "profilo.md",
        BRAIN_DIR / "schemi" / "abitudini.md",
        BRAIN_DIR / "schemi" / "errori-ricorrenti.md",
        BRAIN_DIR / "schemi" / "rischi.md",
        BRAIN_DIR / "regole" / "regole-fondamentali.md",
    ]
    for f in priority_files:
        if f.exists():
            text = f.read_text("utf-8").strip()
            if text:
                parts.append(f"\n\n---\n## {f.stem.upper()}\n{text}")

    areas = ["memoria", "diario", "lavoro", "trading", "finanze",
             "salute", "casa", "relazioni", "progetti", "decisioni"]
    for area in areas:
        area_dir = BRAIN_DIR / area
        if area_dir.exists():
            recent = sorted(area_dir.glob("*.md"),
                            key=lambda x: x.stat().st_mtime, reverse=True)[:3]
            for f in recent:
                text = f.read_text("utf-8").strip()
                if text and len(text) > 30:
                    parts.append(f"\n\n---\n## {area.upper()} — {f.name}\n{text}")

    return "\n".join(parts)


def process_file(filename: str, data: bytes, content_type: str | None) -> dict:
    mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    ext = Path(filename).suffix.lower()

    if mime in SUPPORTED_IMAGE_TYPES:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": mime,
                       "data": base64.standard_b64encode(data).decode()},
        }

    if mime == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(data).decode()},
        }

    if mime.startswith("text/") or ext in {".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml"}:
        try:
            return {"type": "text", "text": f"=== {filename} ===\n{data.decode('utf-8')}\n==="}
        except UnicodeDecodeError:
            pass

    if mime.startswith("video/"):
        return {"type": "text",
                "text": f"[Video: {filename}] — I video non sono analizzabili direttamente. "
                        f"Descrivi cosa mostra o carica degli screenshot."}

    return {"type": "text", "text": f"[File: {filename} ({mime}) — formato non supportato per l'analisi]"}


@app.get("/api/status")
async def status():
    return {"ok": True, "has_key": bool(os.getenv("ANTHROPIC_API_KEY")), "model": MODEL}


@app.post("/api/chat")
async def chat(
    message: str = Form(default=""),
    session_id: str = Form(default=""),
    files: List[UploadFile] = File(default=[]),
):
    client = get_client()
    if not session_id:
        session_id = str(uuid.uuid4())

    history = sessions.setdefault(session_id, [])
    content = []
    attached = []

    for f in files:
        if not f.filename:
            continue
        data = await f.read()
        part = process_file(f.filename, data, f.content_type)
        content.append(part)
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

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=load_system_prompt(),
        messages=history,
    )

    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})

    return {
        "session_id": session_id,
        "response": reply,
        "tokens": {"in": response.usage.input_tokens, "out": response.usage.output_tokens},
    }


@app.post("/api/save")
async def save_note(
    path: str = Form(...),
    content: str = Form(...),
    action: str = Form(default="create"),
):
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
            files = []
            for f in sorted(d.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.name.startswith("."):
                    continue
                files.append({
                    "name": f.name,
                    "path": f"secondo-cervello/{area}/{f.name}",
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y"),
                })
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
