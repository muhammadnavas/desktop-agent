# Desktop Agent

A local-first Windows desktop assistant with natural-language commands, local Ollama intent understanding, and optional offline voice transcription.

## Features

- Text and voice commands to launch Notepad, Calculator, File Explorer, VS Code, or WhatsApp.
- Guarded browser tab controls: open a new tab in a supported focused browser; closing the current tab requires explicit approval.
- Read-only system status for OS, hostname, Python, CPU count, and disk usage.
- Fixed read-only diagnostics such as IP configuration, running process list, current user, Windows system information, and Python/Node/Git/Docker version checks. No arbitrary shell or PowerShell execution.
- File-system browsing and project inspection: list directory contents, enumerate source files, search code, read text files, create folders, and stage file writes for approval.
- Say **“Alexa, code autometa”** to open the AI Browser Automation Agent workspace in Antigravity and start frontend/backend development servers in separate terminal windows.
- Always-on local Alexa wake-word detection with openWakeWord; after activation, one command is captured and transcribed locally with faster-whisper.
- Spoken offline feedback after voice commands using Windows SAPI via pyttsx3, including successful actions, unsupported commands, and errors.
- Local Ollama model interprets natural-language intent. No hosted LLM API key is needed.
- The model can only choose from explicitly registered and validated tools; arbitrary shell commands are never executed.
- Deterministic parser fallback works when Ollama is unavailable.
- Natural-language tool routing: Ollama can select from registered tools, including app launching and read-only active/open-window inspection; tool names and arguments are strictly validated before execution.
- Registered-tool execution: the model can only request explicitly registered actions; tool names, required arguments, extra arguments, and return types are validated, and execution outcomes and failures are logged. Ollama intent JSON is also checked against a strict schema before routing.
- Persistent local memory: explicitly saved facts and preferences are stored in local MongoDB and supplied as context to the local intent model. Nothing is automatically saved from conversations.
- Built-in user context: a concise profile of known projects, technical vocabulary, and common speech-to-text variations is supplied to Ollama to improve intent recognition without granting extra permissions.
- Built-in skills: inspectable procedural guidance for app launching/closing, browser tabs, system status, Code Autometa, visible desktop tasks, voice commands, and file/project management.
- Local screenshot capture and screenshot-aware planning through an Ollama vision model.
- Mouse movement and clicks, safe keyboard navigation, typing, scrolling and bounded waits.
- Every click/move is shown with its target description and coordinates before approval.
- Multi-step tasks are previewed and require explicit, one-time approval before execution.

## Requirements

- Windows 10/11
- Python 3.10+
- [Ollama](https://ollama.com/download) (recommended)
- A working Windows microphone input device

## Install

```powershell
git clone https://github.com/muhammadnavas/desktop-agent.git
cd desktop-agent
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

For always-on Alexa wake-word detection and offline voice transcription, install the voice extras:

```powershell
pip install -e ".[voice,desktop]"
```

## Configure local MongoDB

Install MongoDB Community Server for Windows and start the MongoDB service. The default connection is `mongodb://127.0.0.1:27017`; Desktop Agent creates the `desktop_agent` database and `memories` collection automatically when first used. You can override `DESKTOP_AGENT_MONGO_URI`, `DESKTOP_AGENT_MONGO_DATABASE`, and `DESKTOP_AGENT_MONGO_COLLECTION` in your `.env` file. Copy `.env.example` to `.env` and adjust only if needed. If MongoDB is unavailable, memory API requests return HTTP 503; normal app commands continue without memory context.

## Configure Ollama

Install Ollama, then pull a local model:

```powershell
ollama pull qwen2.5:3b
ollama pull qwen2.5vl:3b
```

Keep Ollama running. Desktop Agent uses these defaults:

- `OLLAMA_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=qwen2.5:3b`
- `WHISPER_MODEL=base` (optional local speech-to-text model)
- `VOICE_RESPONSE_RATE=175` (spoken response speed; supported range 120–220)
- `OLLAMA_VISION_MODEL=qwen2.5vl:3b` (local screenshot-understanding model)

Override them in PowerShell if needed:

```powershell
$env:OLLAMA_MODEL="qwen2.5:3b"
$env:WHISPER_MODEL="base"
```

For a laptop with 4 GB VRAM, start with a quantized 3B Ollama model. Ollama may offload layers to system RAM/CPU depending on available memory. Local Whisper runs on CPU with int8 by default.

## Run manually

```powershell
python -m uvicorn desktop_agent.api:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765.

## Keep Desktop Agent running automatically

To make Alexa available whenever you sign in to Windows, install the user-level
Task Scheduler startup task **after installing the voice and desktop extras**:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_startup.ps1
```

This registers `DesktopAgent-Alexa` to start the hidden background service at
your Windows logon, using the project's `.venv` interpreter when present.
The task is configured to restart the service if it exits unexpectedly. Logs
are written to `%LOCALAPPDATA%\DesktopAgent\logs\agent.log`. The dashboard
is available at `http://127.0.0.1:8765`; check
`http://127.0.0.1:8765/api/voice/status` to confirm the Alexa listener says
`listening`.

To remove automatic startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_startup.ps1
```

The microphone wake listener retries initialization after microphone, model,
or audio-stream failures, with a backoff delay. This works while your Windows
user session is active and the PC is awake. Sleep, hibernate, shutdown, a muted
or disconnected microphone, and Windows microphone privacy permissions can
prevent wake-word detection. This does not install a Windows service or bypass
the normal user-session microphone permissions.

## Hands-free voice commands

1. Install the voice extras with `pip install -e ".[voice,desktop]"`.
2. Start the Desktop Agent API. Its backend listens locally for the **Alexa** wake word.
3. Say **“Alexa”**, then speak a command. Recording stops after a short silence and faster-whisper transcribes it locally.
4. The agent speaks a short response after each command. Detailed results remain available in the dashboard/API; long responses are shortened for speech.
5. Say **“Alexa, code autometa”** (also recognized when transcribed as “Code Automata”, “Code Automate”, or “Code Auto Meta”) to run the fixed development workflow for the AI Browser Automation Agent:
   - Open the project in Antigravity (or use the `agy` CLI if the IDE launcher is not found).
   - Open a terminal in `frontend` and run `npm run dev`.
   - Open another terminal in `backend` and run `uvicorn main:app --reload`.

The default project path is `D:\\Projects\\Python\\ai-browser-automation-agent`. To change it, set `AI_BROWSER_AGENT_ROOT` before starting Desktop Agent. The workflow validates `frontend/package.json` and `backend/main.py` before launching anything. The microphone stays active while the API is running; wake-word detection and transcription run locally. Voice capture now stops after 5 seconds if no command speech follows the wake word, ends after 1.1 seconds of silence, ignores very short noise, and has a 12-second hard limit. These defaults can be tuned with `VOICE_SPEECH_START_TIMEOUT`, `VOICE_SILENCE_SECONDS`, `VOICE_MIN_SPEECH_SECONDS`, `VOICE_SPEECH_RMS_THRESHOLD`, and `VOICE_MAX_COMMAND_SECONDS` environment variables. If your microphone is unusually quiet or noisy, adjust `VOICE_SPEECH_RMS_THRESHOLD` (default `350`) in PowerShell before starting the app. On the first startup, openWakeWord downloads its pretrained model files into its package model directory; this requires an internet connection once. Later startups reuse the downloaded files. Missing voice extras or microphone/model initialization failures no longer prevent the API and dashboard from starting: check `GET /api/diagnostics` and `GET /api/voice/status` for the exact issue and install command.

## CLI

```powershell
python -m desktop_agent "Open Notepad"
```

## API

- `GET /health` — health check
- `GET /api/apps` — supported application allowlist
- `GET /api/tools` — registered agent tools and their required arguments (apps, browser tabs, system status, allowlisted diagnostics, directory/project files, and window inspection)
- `GET /api/skills` and `GET /api/skills/{skill_id}` — discover built-in skills and inspect their instructions
- `GET /api/memories` — list saved memories; supports `q` and `limit`
- `POST /api/memories` — explicitly save a memory using JSON `{\"content\":\"...\",\"category\":\"preference\"}`
- `DELETE /api/memories/{memory_id}` — delete a saved memory
- `GET /api/ollama/status` — Ollama and model status
- `GET /api/diagnostics` — Python platform, Ollama, MongoDB memory connection, optional voice packages, listener state, and desktop dependency diagnostics
- `POST /api/commands` — JSON: `{"text":"Open Notepad","use_ollama":true}`; supports registered workspace file read and staged-write tools
- `POST /api/files/confirm-write` — explicitly approve a staged file write using its one-time confirmation token
- `POST /api/commands/confirm` — approve one exact risk-gated command (closing an app/tab or creating a folder); tokens are single-use and expire after 90 seconds
- `POST /api/voice/transcribe` — multipart upload with field name `audio`
- `GET /api/desktop/screenshot` — capture the primary display
- `POST /api/tasks/plan` — create a screenshot-aware plan without executing it
- `POST /api/tasks/confirm` — execute a plan with its one-time approval token

## User context, memory, skills, and tools

The local intent model receives a built-in, non-sensitive user profile from `desktop_agent/user_context.py`. It describes the user's study area, known projects, tools, and vocabulary, including likely speech-to-text spellings such as Automata/Automate for Code Autometa. This helps resolve imperfect pronunciation and project references. It is context only: tool allowlists, path validation, and confirmation requirements remain unchanged. Edit that module to correct or extend the profile.

## Agent memory, skills, and tools

Memories are stored in the local MongoDB database `desktop_agent`, collection `memories` by default. Configure the connection with `DESKTOP_AGENT_MONGO_URI`, `DESKTOP_AGENT_MONGO_DATABASE`, and `DESKTOP_AGENT_MONGO_COLLECTION`. Only facts explicitly submitted to `POST /api/memories` are saved; do not store passwords, API keys, authentication codes, or other secrets. The model receives the ten most recent saved facts as context. Built-in skills are guidance documents and do not grant additional execution permissions. Actual actions must still pass through the registered tool allowlist. The window-inspection tools are read-only and return window titles/handles only. Natural-language requests such as “What window is active?”, “List open windows”, “Open a new tab”, “Close this tab”, “List files in Downloads”, “Search this project”, and “What are my system specs?” are routed to registered tools. Browser-tab shortcuts only run when a supported browser is the foreground window. Closing a tab and closing an application require a one-time approval through `/api/commands/confirm`. System status is read-only.

## Safety and current scope

- The server binds to localhost by default.
- Only allowlisted apps can be launched.
- Commands use argument arrays and `shell=False`.
- Every desktop plan requires explicit confirmation and expires after two minutes.
- Supported desktop actions are limited to click, type, safe key presses, scroll and short waits; arbitrary shell commands are not supported.
- Move the mouse to the top-left corner for PyAutoGUI's emergency failsafe.
- Do not use this version for passwords, payments, purchases, deleting data or account/security changes. Keep sensitive windows closed.
- Screenshot understanding requires the separate vision model configured by `OLLAMA_VISION_MODEL`; the regular text model cannot interpret screenshots.

## Tests

```powershell
pip install -e ".[dev,desktop,voice]"
pytest -q
```

## Roadmap

1. Session memory, audit logs, retries and recovery
2. Better task verification and interruption handling
3. Wake-word and push-to-talk support


### Windows UI Automation inspection

Install the optional desktop dependencies with `pip install -e ".[desktop]"`. The registered `get_window_controls` tool inspects a visible window by a case-insensitive title substring and returns accessible control names, types, automation IDs, visibility, and enabled state. It deliberately does not read edit-field values or perform actions. Inspection is read-only and Windows-only; actual interaction remains behind the existing screenshot-plan and explicit-confirmation flow.


### Approval-gated UI button clicks

Call `POST /api/ui-actions/plan-click` with `{"window_title":"Notepad","button_name":"Save"}`.
The agent resolves an exact, unique, visible, enabled Button and returns a
90-second, single-use confirmation token. Only after explicit user approval,
call `POST /api/ui-actions/confirm-click` with that token. The target is
resolved again immediately before clicking, so stale or ambiguous controls
will not be clicked. Only UIA controls of type `Button` are supported;
labels associated with sensitive or destructive actions are blocked.
This API is Windows-only.



## Risk-based command execution

Desktop Agent classifies requests before execution:

- **Automatic:** opening an allowlisted app, reading UTF-8 text files, creating folders, and read-only window inspection.
- **Approval required:** closing an app (to avoid losing unsaved work), editing or overwriting a file (preview first), and desktop UI interaction plans.
- **Blocked by default:** destructive file deletion/wiping, drive formatting, security weakening, credential disclosure, payments, and purchases. These requests are rejected before Ollama routing.
- **Unknown tools:** rejected unless explicitly registered and assigned a permission tier.

For an approval-gated command, POST /api/commands returns needs_approval, a description, and a short-lived one-time confirmation_token. Only after the user approves that exact action should the client send the token to POST /api/commands/confirm. The server never executes the pending action just because a model suggested it. All decisions and execution outcomes are logged.

This is a conservative default policy, not a general-purpose shell. Arbitrary PowerShell, CMD, Python scripts, installers, Git commits/pushes, and downloads are not automatically executed.

## Full filesystem access

File tools can access any local path that the Windows account running Desktop Agent is permitted to access. You do not need to configure a workspace. Use an absolute path such as `C:\\Users\\Navas\\Desktop\\notes.txt`, a drive path, or a UNC path. Relative paths resolve from the agent's current working directory (or the optional `DESKTOP_AGENT_WORKSPACE` convenience setting). Parent-directory traversal is allowed. Normal Windows file permissions still apply; the agent cannot bypass administrator permissions, encryption, or files locked by another process.

Reading uses the registered `read_file` tool (UTF-8 text, maximum 1 MB). Writing uses `prepare_file_write`, which stages the exact absolute destination and content and returns a preview plus a one-time confirmation token. Nothing is written until you explicitly approve that exact operation through `POST /api/files/confirm-write`. Approval expires after two minutes and can only be used once. Existing files are atomically replaced only after approval. Binary files are not supported by these text-file tools. Folder creation can target any accessible absolute or relative path.
