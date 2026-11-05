"""Local API for the Desktop Agent."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
import secrets
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from desktop_agent.actions.apps import supported_apps
from desktop_agent.actions.registry import available_tools, execute_tool
from desktop_agent.actions.desktop import capture_screenshot, execute_steps, validate_steps
from desktop_agent.actions.workflows import is_code_autometa_command, start_code_autometa_workflow
from desktop_agent.ollama_client import OllamaError, ollama_status, plan_desktop_task, understand_command
from desktop_agent.parser import parse_command
from desktop_agent.voice import voice_dependencies_status
from desktop_agent.voice_listener import WakeWordListener
from desktop_agent import memory as agent_memory
from desktop_agent.skills import get_skill, list_skills

logger = logging.getLogger(__name__)

_wake_listener: WakeWordListener | None = None


def _handle_wake_command(transcript: str) -> None:
    try:
        execute_command(CommandRequest(text=transcript, use_ollama=True))
    except Exception:
        # Keep the listener alive, but never hide the reason a command failed.
        logger.exception("Could not execute voice command: %s", transcript)


@asynccontextmanager
async def lifespan(_app):
    global _wake_listener
    _wake_listener = WakeWordListener(_handle_wake_command)
    try:
        _wake_listener.start()
    except Exception:
        # A microphone or optional package failure must not prevent the API/UI
        # from starting. The voice status endpoint exposes the failure.
        logger.exception("Could not start wake-word listener")
    try:
        yield
    finally:
        if _wake_listener is not None:
            _wake_listener.stop()


app = FastAPI(
    title="Desktop Agent",
    version="0.2.0",
    description="Local-first Windows desktop assistant with Ollama and offline voice input.",
    lifespan=lifespan,
)
INDEX_FILE = Path(__file__).parent / "web" / "index.html"
_PENDING_TASKS: dict[str, dict] = {}
_BLOCKED_TASK_TERMS = ("password", "passcode", "one-time code", "otp", "payment", "purchase", "checkout", "send money", "transfer money", "bank transfer", "delete", "erase", "format drive", "bank account", "credit card", "security settings", "change password")


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


@app.get("/api/tools")
def get_tools():
    """List the explicitly registered actions available to the agent."""
    return {"tools": available_tools()}


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    category: str = Field(default="general", max_length=40)


@app.get("/api/memories")
def get_memories(q: str | None = None, limit: int = 50):
    try:
        return {"memories": agent_memory.list_memories(q, limit)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/memories")
def create_memory(request: MemoryCreateRequest):
    try:
        return {"success": True, "memory": agent_memory.remember(request.content, request.category)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.delete("/api/memories/{memory_id}")
def remove_memory(memory_id: str):
    try:
        if not agent_memory.delete_memory(memory_id):
            raise HTTPException(status_code=404, detail="Memory not found.")
        return {"success": True, "deleted_id": memory_id}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/skills")
def get_skills():
    return {"skills": list_skills()}


@app.get("/api/skills/{skill_id}")
def get_skill_details(skill_id: str):
    try:
        return get_skill(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Skill not found.") from exc


@app.get("/api/ollama/status")
def get_ollama_status():
    return ollama_status()


@app.get("/api/voice/status")
def get_voice_status():
    if _wake_listener is None:
        return {
            "available": False,
            "state": "not_started",
            "wake_word": "Alexa",
            "last_error": "The application lifespan has not started the listener.",
        }
    return _wake_listener.status()


@app.get("/api/diagnostics")
def get_diagnostics():
    """Return actionable local dependency and service diagnostics."""
    from importlib.util import find_spec
    import platform

    voice = voice_dependencies_status()
    voice["listener"] = get_voice_status()
    desktop_installed = find_spec("pyautogui") is not None
    ollama = ollama_status()
    return {
        "application": {"status": "ok", "python": platform.python_version(), "platform": platform.platform()},
        "ollama": ollama,
        "memory": agent_memory.mongo_status(),
        "voice": voice,
        "desktop": {
            "supported_platform": platform.system() == "Windows",
            "pyautogui_installed": desktop_installed,
            "install_command": "pip install -e .[desktop]" if not desktop_installed else None,
        },
    }


@app.post("/api/commands")
def execute_command(request: CommandRequest):
    # Handle this fixed local workflow before Ollama so the wake phrase is deterministic.
    if is_code_autometa_command(request.text):
        try:
            result = start_code_autometa_workflow()
            return {"success": True, "message": result["message"], "result": result, "source": "workflow"}
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    source = "rules"
    tool_name = None
    tool_arguments: dict = {}
    response_text = ""
    normalized = request.text.lower()

    if request.use_ollama:
        try:
            interpreted = understand_command(request.text)
            source = "ollama"
            tool_name = interpreted.get("tool")
            tool_arguments = interpreted.get("arguments", {})
            response_text = interpreted.get("response", "")
        except OllamaError:
            source = "rules_fallback"

    # Deterministic local routing remains available if Ollama is offline or
    # declines a request that matches one of the explicitly supported tools.
    if tool_name is None:
        launch_intent = parse_command(request.text)
        if launch_intent is not None:
            tool_name = "launch_app"
            tool_arguments = {"app_id": launch_intent.app_id}
        elif any(term in normalized for term in ("active window", "current window", "which app am i using", "what app is open")):
            tool_name = "get_active_window"
        elif any(term in normalized for term in ("open windows", "all windows", "which apps are open", "what windows are open")):
            tool_name = "list_open_windows"

    if tool_name is None:
        raise HTTPException(
            status_code=422,
            detail="I couldn't identify a supported action. Try opening an app or asking which window is active/open.",
        )

    try:
        result = execute_tool(tool_name, tool_arguments)
        default_messages = {
            "launch_app": f"Opening {result.get('app', 'application')}.",
            "get_active_window": f"Active window: {result.get('title') or 'No titled window found.'}",
            "list_open_windows": f"Found {result.get('count', 0)} open windows.",
        }
        return {
            "success": True,
            "message": response_text or default_messages.get(tool_name, "Action completed."),
            "result": result,
            "source": source,
            "tool": tool_name,
        }
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Windows could not complete the action: {exc}") from exc

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

        from desktop_agent.voice import transcribe_audio

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
