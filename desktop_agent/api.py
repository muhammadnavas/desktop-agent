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
from desktop_agent.voice import speak_text, voice_dependencies_status
from desktop_agent.voice_listener import WakeWordListener
from desktop_agent import memory as agent_memory
from desktop_agent.skills import get_skill, list_skills

logger = logging.getLogger(__name__)

from desktop_agent.logging_config import configure_logging

_wake_listener: WakeWordListener | None = None


def _handle_wake_command(transcript: str) -> None:
    """Execute a spoken command and speak its actual outcome."""
    logger.info("VOICE COMMAND RECEIVED | transcript=%r", transcript)
    try:
        result = execute_command(CommandRequest(text=transcript, use_ollama=True))
        response = result.get("message") or "Command completed."
        logger.info("AGENT RESPONSE | success=%s source=%s tool=%s response=%s", result.get("success"), result.get("source"), result.get("tool", "workflow"), response)
    except HTTPException as exc:
        detail = exc.detail
        response = detail if isinstance(detail, str) else "I couldn't complete that command."
        logger.warning("VOICE COMMAND FAILED | transcript=%r | response=%s", transcript, response)
    except Exception:
        response = "Something went wrong while running that command. Check the Desktop Agent logs."
        logger.exception("Could not execute voice command: %s", transcript)

    logger.info("VOICE RESPONSE | %s", response)
    try:
        speak_text(response)
    except Exception:
        # Speech output is optional and must never stop the wake-word listener.
        logger.exception("Could not speak the voice command response")


@asynccontextmanager
async def lifespan(_app):
    global _wake_listener
    log_file = configure_logging()
    logger.info("Desktop Agent started | activity_log=%s", log_file)
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
_PENDING_UI_ACTIONS: dict[str, dict] = {}
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
    uia_installed = find_spec("pywinauto") is not None
    ollama = ollama_status()
    return {
        "application": {"status": "ok", "python": platform.python_version(), "platform": platform.platform()},
        "ollama": ollama,
        "memory": agent_memory.mongo_status(),
        "voice": voice,
        "desktop": {
            "supported_platform": platform.system() == "Windows",
            "pyautogui_installed": desktop_installed,
            "pywinauto_installed": uia_installed,
            "install_command": 'pip install -e ".[desktop]"' if not (desktop_installed and uia_installed) else None,
        },
    }


@app.post("/api/commands")
def execute_command(request: CommandRequest):
    logger.info("COMMAND RECEIVED | text=%r | ollama=%s", request.text, request.use_ollama)
    # Handle this fixed local workflow before Ollama so the wake phrase is deterministic.
    if is_code_autometa_command(request.text):
        logger.info("ACTION START | tool=code_autometa_workflow")
        try:
            result = start_code_autometa_workflow()
            logger.info("ACTION SUCCESS | tool=code_autometa_workflow | result=%s", result)
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
        logger.warning("COMMAND UNHANDLED | text=%r | source=%s", request.text, source)
        raise HTTPException(
            status_code=422,
            detail="I couldn't identify a supported action. Try opening an app or asking which window is active/open.",
        )

    try:
        logger.info("ACTION START | tool=%s | arguments=%s | source=%s", tool_name, tool_arguments, source)
        result = execute_tool(tool_name, tool_arguments)
        logger.info("ACTION SUCCESS | tool=%s | result=%s", tool_name, result)
        default_messages = {
            "launch_app": f"Opening {result.get('app', 'application')}.",
            "get_active_window": f"Active window: {result.get('title') or 'No titled window found.'}",
            "list_open_windows": f"Found {result.get('count', 0)} open windows.",
            "read_file": f"Read {result.get('path', 'the requested file')}.",
            "prepare_file_write": (
                f"Prepared {result.get('path', 'the requested file')} for review. "
                f"{'This will overwrite the existing file. ' if result.get('overwrites_existing') else ''}"
                "Nothing has been written yet. Review the preview and explicitly confirm the one-time token."
            ),
        }
        return {
            "success": True,
            "message": default_messages[tool_name] if tool_name == "prepare_file_write" else (response_text or default_messages.get(tool_name, "Action completed.")),
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

class UIButtonClickRequest(BaseModel):
    window_title: str = Field(min_length=1, max_length=200)
    button_name: str = Field(min_length=1, max_length=120)


class UIActionConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=128)

class FileWriteConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=128)


class TaskConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=128)


@app.post("/api/ui-actions/plan-click")
def plan_ui_button_click(request: UIButtonClickRequest):
    """Resolve an exact button target and issue a short-lived one-time approval."""
    try:
        from desktop_agent.actions.windows_uia import inspect_button_target

        target = inspect_button_target(request.window_title, request.button_name)
        token = secrets.token_urlsafe(32)
        _PENDING_UI_ACTIONS[token] = {
            "window_title": target["window_title"],
            "button_name": target["button_name"],
            "created_at": time.monotonic(),
        }
        now = time.monotonic()
        for key in list(_PENDING_UI_ACTIONS):
            if now - _PENDING_UI_ACTIONS[key]["created_at"] > 90:
                _PENDING_UI_ACTIONS.pop(key, None)
        return {
            "target": target,
            "confirmation_token": token,
            "expires_in_seconds": 90,
            "requires_confirmation": True,
            "message": f"Ready to click '{target['button_name']}' in '{target['window_title']}'. Approve this exact action to continue.",
        }
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ui-actions/confirm-click")
def confirm_ui_button_click(request: UIActionConfirmRequest):
    pending = _PENDING_UI_ACTIONS.pop(request.confirmation_token, None)
    if not pending:
        raise HTTPException(status_code=404, detail="This approval is invalid, expired, or already used. Create a new approval.")
    if time.monotonic() - pending["created_at"] > 90:
        raise HTTPException(status_code=410, detail="This approval expired. Inspect the button again.")
    try:
        from desktop_agent.actions.windows_uia import click_button

        result = click_button(pending["window_title"], pending["button_name"])
        return {"success": True, "result": result}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Windows could not click the button: {exc}") from exc


@app.post("/api/files/confirm-write")
def confirm_file_write_endpoint(request: FileWriteConfirmRequest):
    """Commit a staged file write only after explicit user confirmation."""
    from desktop_agent.actions.files import confirm_file_write

    try:
        return confirm_file_write(request.confirmation_token)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
