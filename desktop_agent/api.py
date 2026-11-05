"""Local API for the Desktop Agent."""

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from desktop_agent.actions.apps import launch_app, supported_apps
from desktop_agent.ollama_client import OllamaError, ollama_status, understand_command
from desktop_agent.parser import LaunchIntent, parse_command
from desktop_agent.voice import transcribe_audio

app = FastAPI(
    title="Desktop Agent",
    version="0.2.0",
    description="Local-first Windows desktop assistant with Ollama and offline voice input.",
)
INDEX_FILE = Path(__file__).parent / "web" / "index.html"


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    use_ollama: bool = True


@app.get("/")
def home():
    return FileResponse(INDEX_FILE)


@app.get("/health")
def health():
    return {"status": "ok", "name": "Desktop Agent", "version": "0.2.0"}


@app.get("/api/apps")
def get_apps():
    return {"apps": supported_apps()}


@app.get("/api/ollama/status")
def get_ollama_status():
    return ollama_status()


@app.post("/api/commands")
def execute_command(request: CommandRequest):
    intent = None
    source = "rules"
    response_text = ""

    if request.use_ollama:
        try:
            interpreted = understand_command(request.text)
            source = "ollama"
            response_text = interpreted["response"]
            if interpreted["action"] == "launch_app":
                intent = LaunchIntent(app_id=interpreted["app_id"])
            else:
                return {
                    "success": False,
                    "message": response_text or "I can't perform that action yet.",
                    "source": source,
                }
        except OllamaError:
            # Local deterministic parser remains available when Ollama is stopped.
            source = "rules_fallback"

    if intent is None:
        intent = parse_command(request.text)

    if intent is None:
        raise HTTPException(
            status_code=422,
            detail="I couldn't identify a supported action. Try asking me to open Notepad, Calculator, File Explorer or VS Code.",
        )

    try:
        result = launch_app(intent.app_id)
        return {
            "success": True,
            "message": response_text or f"Opening {result['app']}.",
            "result": result,
            "source": source,
        }
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Windows could not launch the app: {exc}") from exc


@app.post("/api/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    suffix = Path(audio.filename or "recording.webm").suffix.lower()
    try:
        # Read in bounded chunks so a large upload is rejected before it is
        # fully buffered in memory.
        chunks: list[bytes] = []
        total_bytes = 0
        max_bytes = 20 * 1024 * 1024
        while True:
            chunk = await audio.read(min(1024 * 1024, max_bytes + 1 - total_bytes))
            if not chunk:
                break
            chunks.append(chunk)
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                raise HTTPException(status_code=413, detail="Audio file is too large (20 MB limit).")

        transcript = transcribe_audio(b"".join(chunks), suffix)
        return {"success": True, "text": transcript}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await audio.close()
