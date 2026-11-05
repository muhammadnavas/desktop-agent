# Desktop Agent

A local-first Windows desktop assistant with natural-language commands, local Ollama intent understanding, and optional offline voice transcription.

## Features

- Text commands to launch Notepad, Calculator, File Explorer, or VS Code.
- Say **“Alexa, code autometa”** to open the AI Browser Automation Agent workspace in Antigravity and start frontend/backend development servers in separate terminal windows.
- Always-on local Alexa wake-word detection with openWakeWord; after activation, one command is captured and transcribed locally with faster-whisper.
- Local Ollama model interprets natural-language intent. No hosted LLM API key is needed.
- The model can only choose from a fixed application allowlist; arbitrary shell commands are never executed.
- Deterministic parser fallback works when Ollama is unavailable.
- Read-only Windows awareness: inspect the active window and list visible open windows through registered tools (no UI interaction or shell access).
- Registered-tool execution: the model can only request explicitly registered actions; tool names, required arguments, extra arguments, and return types are validated, and execution outcomes and failures are logged. Ollama intent JSON is also checked against a strict schema before routing.\n- Persistent local memory: explicitly saved facts and preferences are stored in local MongoDB and supplied as context to the local intent model. Nothing is automatically saved from conversations.\n- Built-in skills: inspectable procedural guidance for app launching, Code Autometa, visible desktop tasks, and voice commands.
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
- `OLLAMA_VISION_MODEL=qwen2.5vl:3b` (local screenshot-understanding model)

Override them in PowerShell if needed:

```powershell
$env:OLLAMA_MODEL="qwen2.5:3b"
$env:WHISPER_MODEL="base"
```

For a laptop with 4 GB VRAM, start with a quantized 3B Ollama model. Ollama may offload layers to system RAM/CPU depending on available memory. Local Whisper runs on CPU with int8 by default.

## Run

```powershell
uvicorn desktop_agent.api:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765.

## Hands-free voice commands

1. Install the voice extras with `pip install -e ".[voice,desktop]"`.
2. Start the Desktop Agent API. Its backend listens locally for the **Alexa** wake word.
3. Say **“Alexa”**, then speak a command. Recording stops after a short silence and faster-whisper transcribes it locally.
4. Say **“Alexa, code autometa”** to run the fixed development workflow for the AI Browser Automation Agent:
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
- `GET /api/tools` — registered agent tools and their required arguments (app launch, active-window inspection, open-window listing)\n- `GET /api/skills` and `GET /api/skills/{skill_id}` — discover built-in skills and inspect their instructions\n- `GET /api/memories` — list saved memories; supports `q` and `limit`\n- `POST /api/memories` — explicitly save a memory using JSON `{\"content\":\"...\",\"category\":\"preference\"}`\n- `DELETE /api/memories/{memory_id}` — delete a saved memory
- `GET /api/ollama/status` — Ollama and model status
- `GET /api/diagnostics` — Python platform, Ollama, MongoDB memory connection, optional voice packages, listener state, and desktop dependency diagnostics
- `POST /api/commands` — JSON: `{"text":"Open Notepad","use_ollama":true}`
- `POST /api/voice/transcribe` — multipart upload with field name `audio`
- `GET /api/desktop/screenshot` — capture the primary display
- `POST /api/tasks/plan` — create a screenshot-aware plan without executing it
- `POST /api/tasks/confirm` — execute a plan with its one-time approval token

## Agent memory, skills, and tools\n\nMemories are stored in the local MongoDB database `desktop_agent`, collection `memories` by default. Configure the connection with `DESKTOP_AGENT_MONGO_URI`, `DESKTOP_AGENT_MONGO_DATABASE`, and `DESKTOP_AGENT_MONGO_COLLECTION`. Only facts explicitly submitted to `POST /api/memories` are saved; do not store passwords, API keys, authentication codes, or other secrets. The model receives the ten most recent saved facts as context. Built-in skills are guidance documents and do not grant additional execution permissions. Actual actions must still pass through the registered tool allowlist. The window-inspection tools are read-only and return window titles/handles only.\n\n## Safety and current scope

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
