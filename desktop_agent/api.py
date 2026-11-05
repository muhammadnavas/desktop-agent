"""Local API for the Desktop Agent."""

from pathlib import Path
import secrets
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from desktop_agent.actions.apps import launch_app, supported_apps
from desktop_agent.actions.desktop import capture_screenshot, execute_steps, validate_steps
from desktop_agent.ollama_client import OllamaError, ollama_status, plan_desktop_task, understand_command
from desktop_agent.parser import LaunchIntent, parse_command
from desktop_agent.voice import transcribe_audio

app = FastAPI(
    title="Desktop Agent",
    version="0.2.0",
    description="Local-first Windows desktop assistant with Ollama and offline voice input.",
)
INDEX_FILE = Path(__file__).parent / "web" / "index.html"
_PENDING_TASKS: dict[str, dict] = {}
_BLOCKED_TASK_TERMS = ("password", "passcode", "one-time code", "otp", "payment", "purchase", "checkout", "delete", "erase", "format drive", "bank account", "credit card", "security settings", "change password")


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
            allowed_app_ids = {item["id"] for item in supported_apps()}
            if interpreted.get("action") == "launch_app" and interpreted.get("app_id") in allowed_app_ids:
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


class TaskPlanRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class TaskConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=128)


@app.get("/api/desktop/screenshot")
def desktop_screenshot():
    try:
        return capture_screenshot()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/tasks/plan")
def create_task_plan(request: TaskPlanRequest):
    if any(term in request.text.lower() for term in _BLOCKED_TASK_TERMS):
        raise HTTPException(status_code=403, detail="This task involves a sensitive or destructive operation and is not supported by Desktop Agent.")
    try:
        screen = capture_screenshot()
        # The vision model receives the actual screenshot, not guessed UI state.
        raw_plan = plan_desktop_task(
            request.text,
            screen["width"],
            screen["height"],
            screen["image"].split(",", 1)[1],
        )
        steps = validate_steps(raw_plan.get("steps"))
        if not steps:
            raise HTTPException(
                status_code=422,
                detail=raw_plan.get("summary") or "The vision model could not create a safe actionable plan.",
            )
        token = secrets.token_urlsafe(32)
        _PENDING_TASKS[token] = {
            "steps": steps,
            "width": screen["width"],
            "height": screen["height"],
            "created_at": time.monotonic(),
            "summary": raw_plan["summary"],
        }
        # Expire stale approvals to prevent delayed execution.
        now = time.monotonic()
        for key in list(_PENDING_TASKS):
            if now - _PENDING_TASKS[key]["created_at"] > 120:
                _PENDING_TASKS.pop(key, None)
        return {
            "summary": raw_plan["summary"],
            "steps": steps,
            "confirmation_token": token,
            "expires_in_seconds": 120,
            "requires_confirmation": True,
            "screenshot": screen,
        }
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tasks/confirm")
def confirm_task(request: TaskConfirmRequest):
    pending = _PENDING_TASKS.pop(request.confirmation_token, None)
    if not pending:
        raise HTTPException(status_code=404, detail="This approval is invalid, expired, or already used. Create a new plan.")
    if time.monotonic() - pending["created_at"] > 120:
        raise HTTPException(status_code=410, detail="This approval expired. Create a new plan.")
    try:
        results = execute_steps(pending["steps"], pending["width"], pending["height"])
        screenshot = capture_screenshot()
        return {
            "success": True,
            "summary": pending["summary"],
            "steps": results,
            "screenshot": screenshot,
        }
    except (RuntimeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
