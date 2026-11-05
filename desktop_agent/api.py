"""Local API for the Desktop Agent."""

from contextlib import asynccontextmanager
import logging
import re
from pathlib import Path
import secrets
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from desktop_agent.actions.apps import supported_apps
from desktop_agent.permissions import classify_command_text, classify_tool
from desktop_agent.actions.registry import available_tools, execute_tool
from desktop_agent.actions.desktop import capture_screenshot, execute_steps, validate_steps
from desktop_agent.actions.workflows import is_code_autometa_command, start_code_autometa_workflow
from desktop_agent.ollama_client import OllamaError, ollama_status, plan_desktop_task, understand_command
from desktop_agent.parser import parse_command, parse_close_command, parse_create_folder_command, normalize_spoken_command
from desktop_agent.voice import speak_text, voice_dependencies_status
from desktop_agent.voice_listener import WakeWordListener
from desktop_agent import memory as agent_memory
from desktop_agent.skills import get_skill, list_skills

logger = logging.getLogger(__name__)

from desktop_agent.logging_config import configure_logging

_wake_listener: WakeWordListener | None = None
_last_voice_activity: dict = {"transcript": "", "response": "", "pending_approval": None}


def _voice_approval_intent(transcript: str) -> str | None:
    """Recognize deliberately short approval phrases; never ask Ollama to interpret them."""
    phrase = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", normalize_spoken_command(transcript))).strip()
    if phrase in {"yes", "yes approve", "approve", "approved", "confirm", "confirm it", "go ahead", "do it", "proceed"}:
        return "approve"
    if phrase in {"no", "no reject", "reject", "deny", "dont", "do not", "cancel", "cancel it", "stop"}:
        return "reject"
    return None


def _handle_voice_approval(transcript: str, intent: str) -> str:
    """Approve/reject only the exact still-pending action created by voice."""
    pending = _last_voice_activity.get("pending_approval")
    if not pending or not pending.get("token"):
        return "There isn't a pending voice approval."
    token = pending["token"]
    request = CommandConfirmRequest(confirmation_token=token)
    if intent == "approve":
        result = confirm_command(request)
        response = result.get("message") or "Approved action completed."
    else:
        result = cancel_command(request)
        response = "Rejected. No changes were made."
    _last_voice_activity["pending_approval"] = None
    return response


def _handle_wake_command(transcript: str) -> None:
    """Execute a spoken command or resolve an explicitly pending voice approval."""
    logger.info("VOICE COMMAND RECEIVED | transcript=%r", transcript)
    intent = _voice_approval_intent(transcript)
    try:
        if intent:
            response = _handle_voice_approval(transcript, intent)
            _last_voice_activity.update({"transcript": transcript, "response": response})
        elif _last_voice_activity.get("pending_approval"):
            pending = _last_voice_activity["pending_approval"]
            token = pending.get("token")
            stored = _PENDING_COMMAND_APPROVALS.get(token) if token else None
            if stored and time.monotonic() - stored["created_at"] <= 90:
                response = (
                    "There is already an action waiting for approval. "
                    "Say Alexa, yes to approve it or Alexa, no to reject it."
                )
                _last_voice_activity.update({"transcript": transcript, "response": response})
            else:
                if token:
                    _PENDING_COMMAND_APPROVALS.pop(token, None)
                _last_voice_activity.update({
                    "transcript": transcript,
                    "response": "That approval has expired. Please repeat your command.",
                    "pending_approval": None,
                })
                response = _last_voice_activity["response"]
        else:
            result = execute_command(CommandRequest(text=transcript, use_ollama=True, session_id="voice"))
            response = result.get("message") or "Command completed."
            _last_voice_activity.update({
                "transcript": transcript,
                "response": response,
                "pending_approval": {
                    "token": result.get("confirmation_token"),
                    "tool": result.get("tool"),
                    "message": response,
                    "expires_in_seconds": result.get("expires_in_seconds", 90),
                } if result.get("needs_approval") and result.get("confirmation_token") else None,
            })
            logger.info("AGENT RESPONSE | success=%s source=%s tool=%s response=%s", result.get("success"), result.get("source"), result.get("tool", "workflow"), response)
    except HTTPException as exc:
        detail = exc.detail
        response = detail if isinstance(detail, str) else "I couldn't complete that command."
        _last_voice_activity.update({"transcript": transcript, "response": response, "pending_approval": None})
        logger.warning("VOICE COMMAND FAILED | transcript=%r | response=%s", transcript, response)
    except Exception:
        response = "Something went wrong while running that command. Check the Desktop Agent logs."
        _last_voice_activity.update({"transcript": transcript, "response": response, "pending_approval": None})
        logger.exception("Could not execute voice command: %s", transcript)

    logger.info("VOICE RESPONSE | %s", response)
    try:
        speak_text(response)
    except Exception:
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
_PENDING_COMMAND_APPROVALS: dict[str, dict] = {}
_BLOCKED_TASK_TERMS = ("password", "passcode", "one-time code", "otp", "payment", "purchase", "checkout", "send money", "transfer money", "bank transfer", "delete", "erase", "format drive", "bank account", "credit card", "security settings", "change password")


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    use_ollama: bool = True
    session_id: str = Field(default="default", min_length=1, max_length=80)


class CommandConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=32, max_length=128)


_PENDING_CLARIFICATIONS: dict[str, str] = {}
# Short-lived in-memory context, isolated per UI/voice session.
_CONVERSATION_HISTORY: dict[str, list[dict[str, str]]] = {}


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
    return {**_wake_listener.status(), "last_response": _last_voice_activity["response"],
            "last_voice_activity": dict(_last_voice_activity)}


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
    logger.info("COMMAND RECEIVED | text=%r | ollama=%s | session=%s", request.text, request.use_ollama, request.session_id)
    command_permission = classify_command_text(request.text)
    if command_permission.level == "blocked":
        logger.warning("COMMAND BLOCKED | text=%r | reason=%s", request.text, command_permission.reason)
        return {"success": False, "blocked": True, "message": command_permission.reason, "source": "permission_policy"}
    normalized_request = normalize_spoken_command(request.text)
    if "tab" in normalized_request and any(word in normalized_request.split() for word in ("close", "shut", "remove")):
        current_tab_phrases = ("this tab", "current tab", "active tab", "close tab", "close this tab", "close current tab", "close browser tab")
        if not any(phrase in normalized_request for phrase in current_tab_phrases):
            return {
                "success": False,
                "message": "I can't identify or close a particular browser tab by its title or website yet. I did not close anything. I can only close the currently active tab after approval.",
                "source": "capability_guard",
            }
    previous = _PENDING_CLARIFICATIONS.pop(request.session_id, None)
    if previous:
        prior_folder = parse_create_folder_command(previous)
        if prior_folder is not None and not prior_folder.folder_name:
            command_text = "create folder called " + request.text.strip()
        elif prior_folder is not None and prior_folder.folder_name and not prior_folder.destination:
            command_text = "create folder called " + prior_folder.folder_name + " in " + request.text.strip()
        else:
            command_text = "Original request: " + previous + " User clarification: " + request.text
    else:
        command_text = request.text
    # Handle this fixed local workflow before Ollama so the wake phrase is deterministic.
    if is_code_autometa_command(command_text):
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
    normalized = normalize_spoken_command(command_text)
    folder_intent = parse_create_folder_command(command_text)
    if folder_intent is not None:
        if not folder_intent.folder_name:
            _PENDING_CLARIFICATIONS[request.session_id] = command_text
            return {"success": True, "needs_clarification": True, "message": "What should I name the folder?", "source": "rules"}
        if not folder_intent.destination:
            _PENDING_CLARIFICATIONS[request.session_id] = command_text
            question = "Where should I create '" + folder_intent.folder_name + "' inside your configured workspace? For example, Documents or Projects."
            return {"success": True, "needs_clarification": True, "message": question, "source": "rules"}
        tool_name = "create_folder"
        tool_arguments = {"path": folder_intent.destination + "/" + folder_intent.folder_name}
        source = "rules"

    if tool_name is None:
        deterministic_close = parse_close_command(command_text)
        if deterministic_close is not None:
            tool_name = "close_app"
            tool_arguments = {"app_id": deterministic_close.app_id}
            source = "rules"

    interpreted = {}
    if tool_name is None and request.use_ollama:
        try:
            history = _CONVERSATION_HISTORY.setdefault(request.session_id, [])
            history.append({"role": "user", "content": command_text[:1000]})
            history[:] = history[-10:]
            interpreted = understand_command(command_text, conversation_history=history[:-1])
            source = "ollama"
            tool_name = interpreted.get("tool")
            tool_arguments = interpreted.get("arguments", {})
            response_text = interpreted.get("response", "")
            assistant_context = (
                "Selected tool: " + str(tool_name)
                + "; arguments: " + str(tool_arguments)
                + "; response: " + response_text
                + ("; clarification: " + interpreted["clarification_question"]
                   if interpreted.get("clarification_question") else "")
            )
            history.append({"role": "assistant", "content": assistant_context[:1200]})
            history[:] = history[-10:]
        except OllamaError:
            source = "rules_fallback"

    # Deterministic local routing remains available if Ollama is offline or
    # declines a request that matches one of the explicitly supported tools.
    if tool_name is None:
        close_intent = parse_close_command(command_text)
        launch_intent = parse_command(command_text)
        if close_intent is not None:
            tool_name = "close_app"
            tool_arguments = {"app_id": close_intent.app_id}
        elif launch_intent is not None:
            tool_name = "launch_app"
            tool_arguments = {"app_id": launch_intent.app_id}
        elif any(term in normalized for term in ("active window", "current window", "which app am i using", "what app is open")):
            tool_name = "get_active_window"
        elif any(term in normalized for term in ("open windows", "all windows", "which apps are open", "what windows are open")):
            tool_name = "list_open_windows"
        elif any(term in normalized for term in ("open a new tab", "new browser tab", "open new tab")):
            tool_name = "open_new_tab"
        elif any(term in normalized for term in ("close this tab", "close current tab", "close browser tab")):
            tool_name = "close_current_tab"
        elif any(term in normalized for term in ("system status", "system information", "system specs", "cpu information", "disk space")):
            tool_name = "get_system_status"
        elif any(verb in normalized for verb in ("run ", "show ", "check ", "list ")):
            diagnostic_aliases = {
                "ipconfig": "ipconfig", "tasklist": "tasklist", "whoami": "whoami",
                "systeminfo": "systeminfo", "system info": "systeminfo",
                "python version": "python_version", "node version": "node_version",
                "git version": "git_version", "docker version": "docker_version",
            }
            for phrase, command_id in diagnostic_aliases.items():
                if phrase in normalized:
                    tool_name = "run_diagnostic_command"
                    tool_arguments = {"command_id": command_id}
                    break

    clarification_question = interpreted.get("clarification_question", "") if request.use_ollama and source == "ollama" else ""
    if clarification_question:
        _PENDING_CLARIFICATIONS[request.session_id] = command_text
        return {"success": True, "needs_clarification": True, "message": clarification_question, "source": source}


    if tool_name == "launch_app":
        app_id = tool_arguments.get("app_id")
        app_patterns = {
            "notepad": r"\bnotepad\b",
            "calculator": r"\b(calculator|calc)\b",
            "explorer": r"\b(explorer|file explorer)\b",
            "vscode": r"\b(vs\s*code|visual studio code|code editor)\b",
            "whatsapp": r"\b(whatsapp|whats\s*app)\b",
        }
        pattern = app_patterns.get(app_id)
        if not pattern or not re.search(pattern, normalized):
            _PENDING_CLARIFICATIONS[request.session_id] = command_text
            question = "I heard a request to open an app, but could not confidently identify '" + str(app_id) + "'. Which supported app did you mean: Notepad, Calculator, File Explorer, VS Code, or WhatsApp?"
            return {"success": True, "needs_clarification": True, "message": question, "source": source}

    if tool_name is None:
        logger.warning("COMMAND UNHANDLED | text=%r | source=%s", command_text, source)
        raise HTTPException(
            status_code=422,
            detail="I couldn't identify a supported action. Try opening an app or asking which window is active/open.",
        )

    permission = classify_tool(tool_name)
    if permission.level == "blocked":
        logger.warning("ACTION BLOCKED | tool=%s | reason=%s", tool_name, permission.reason)
        return {"success": False, "blocked": True, "message": permission.reason,
                "source": "permission_policy", "tool": tool_name}
    if permission.level == "approval" and tool_name != "prepare_file_write":
        now = time.monotonic()
        for key in list(_PENDING_COMMAND_APPROVALS):
            if now - _PENDING_COMMAND_APPROVALS[key]["created_at"] > 90:
                _PENDING_COMMAND_APPROVALS.pop(key, None)
        token = secrets.token_urlsafe(32)
        _PENDING_COMMAND_APPROVALS[token] = {
            "tool": tool_name,
            "arguments": dict(tool_arguments),
            "created_at": now,
        }
        logger.info("ACTION AWAITING APPROVAL | tool=%s | arguments=%s", tool_name, tool_arguments)
        return {
            "success": True,
            "needs_approval": True,
            "confirmation_token": token,
            "expires_in_seconds": 90,
            "tool": tool_name,
            "message": permission.reason + " Approve this exact action to continue.",
            "source": source,
        }

    try:
        logger.info("ACTION START | tool=%s | arguments=%s | source=%s | permission=%s", tool_name, tool_arguments, source, permission.level)
        result = execute_tool(tool_name, tool_arguments)
        logger.info("ACTION SUCCESS | tool=%s | result=%s", tool_name, result)
        window_titles = [item.get("title", "") for item in result.get("windows", []) if item.get("title")]
        file_excerpt = str(result.get("content", "")).strip()
        if len(file_excerpt) > 280:
            file_excerpt = file_excerpt[:277].rsplit(" ", 1)[0] + "..."
        matches = result.get("matches", [])
        system_disk = result.get("disk", {})
        free_bytes = system_disk.get("free_bytes")
        default_messages = {
            "launch_app": f"Opening {result.get('app', 'application')}.",
            "close_app": f"Close requested for {result.get('app', 'application')}.",
            "create_folder": f"Created folder {result.get('path', 'in the selected location')}.",
            "get_active_window": f"Your active window is {result.get('title') or 'untitled'}.",
            "list_open_windows": f"Found {result.get('count', 0)} open windows" + (": " + ", ".join(window_titles[:5]) if window_titles else "."),
            "open_new_tab": f"Opened a new tab in {result.get('window', 'your browser')}.",
            "close_current_tab": f"Closed the current tab in {result.get('window', 'your browser')}.",
            "get_system_status": f"Your system is {result.get('system', 'running')} {result.get('release', '')}, with {result.get('logical_cpu_count') or 'an unknown number of'} logical CPUs" + (f" and {free_bytes / (1024 ** 3):.1f} GB free on {system_disk.get('root', 'the main drive')}." if isinstance(free_bytes, int) else "."),
            "run_diagnostic_command": f"Diagnostic {result.get('command_id', 'command')} {'completed' if result.get('success') else 'returned an error'}." + (": " + str(result.get("output", ""))[:280] if result.get("output") else ""),
            "list_directory": f"Found {result.get('count', 0)} items in {result.get('path', 'the directory')}." + (": " + ", ".join(item.get("name", "") for item in result.get("entries", [])[:8]) if result.get("entries") else " The directory is empty."),
            "read_file": f"Read {result.get('path', 'the requested file')}." + (f" The content starts: {file_excerpt}" if file_excerpt else " The file is empty."),
            "list_project_files": f"Found {result.get('count', 0)} project files" + (": " + ", ".join(result.get("files", [])[:8]) if result.get("files") else "."),
            "search_project": f"Found {len(matches)} matches in {result.get('files_inspected', 0)} files" + (": " + "; ".join(f"{m.get('file')} line {m.get('line')}" for m in matches[:5]) if matches else "."),
            "prepare_file_write": (
                f"Prepared {result.get('path', 'the requested file')} for review. "
                f"{'This will overwrite the existing file. ' if result.get('overwrites_existing') else ''}"
                "Nothing has been written yet. Review the preview and explicitly confirm the one-time token."
            ),
        }
        return {
            "success": True,
            "message": default_messages.get(tool_name, response_text or "Action completed."),
            "result": result,
            "source": source,
            "tool": tool_name,
        }
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Windows could not complete the action: {exc}") from exc



@app.post("/api/commands/cancel")
def cancel_command(request: CommandConfirmRequest):
    """Discard a pending approval without executing its action."""
    pending = _PENDING_COMMAND_APPROVALS.pop(request.confirmation_token, None)
    if not pending:
        raise HTTPException(status_code=404, detail="This approval is invalid, expired, or already used.")
    voice_pending = _last_voice_activity.get("pending_approval") or {}
    if voice_pending.get("token") == request.confirmation_token:
        _last_voice_activity["pending_approval"] = None
    return {"success": True, "cancelled": True, "tool": pending["tool"]}


@app.post("/api/commands/confirm")
def confirm_command(request: CommandConfirmRequest):
    """Execute a previously reviewed command action exactly once."""
    pending = _PENDING_COMMAND_APPROVALS.pop(request.confirmation_token, None)
    if not pending:
        raise HTTPException(status_code=404, detail="This approval is invalid, expired, or already used. Submit the command again.")
    if time.monotonic() - pending["created_at"] > 90:
        voice_pending = _last_voice_activity.get("pending_approval") or {}
        if voice_pending.get("token") == request.confirmation_token:
            _last_voice_activity["pending_approval"] = None
        raise HTTPException(status_code=410, detail="This approval expired. Submit the command again.")
    voice_pending = _last_voice_activity.get("pending_approval") or {}
    if voice_pending.get("token") == request.confirmation_token:
        _last_voice_activity["pending_approval"] = None
    tool_name = pending["tool"]
    if classify_tool(tool_name).level != "approval":
        raise HTTPException(status_code=403, detail="This action is no longer eligible for approval.")
    try:
        result = execute_tool(tool_name, pending["arguments"])
        messages = {
            "close_app": f"Close requested for {result.get('app', 'the application')}.",
            "close_current_tab": f"Closed the current tab in {result.get('window', 'your browser')}.",
        }
        return {"success": True, "tool": tool_name, "result": result,
                "message": messages.get(tool_name, "Approved action completed."),
                "source": "approved"}
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Windows could not complete the approved action: {exc}") from exc


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


@app.post("/api/files/cancel-write")
def cancel_file_write_endpoint(request: FileWriteConfirmRequest):
    """Discard a staged file write without modifying the target."""
    from desktop_agent.actions.files import cancel_file_write

    try:
        return cancel_file_write(request.confirmation_token)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
