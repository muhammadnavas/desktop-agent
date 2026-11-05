# Desktop Agent

A local-first Windows desktop assistant with natural-language commands, local Ollama intent understanding, and optional offline voice transcription.

## Features

- Text commands to launch Notepad, Calculator, File Explorer, or VS Code.
- Voice input recorded in the browser and transcribed locally with faster-whisper.
- Local Ollama model interprets natural-language intent. No hosted LLM API key is needed.
- The model can only choose from a fixed application allowlist; arbitrary shell commands are never executed.
- Deterministic parser fallback works when Ollama is unavailable.

## Requirements

- Windows 10/11
- Python 3.10+
- [Ollama](https://ollama.com/download) (recommended)
- Chrome or Edge for microphone recording

## Install

```powershell
git clone https://github.com/muhammadnavas/desktop-agent.git
cd desktop-agent
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

For offline voice transcription, install the optional dependency:

```powershell
pip install -e ".[voice]"
```

## Configure Ollama

Install Ollama, then pull a local model:

```powershell
ollama pull qwen2.5:3b
```

Keep Ollama running. Desktop Agent uses these defaults:

- `OLLAMA_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=qwen2.5:3b`
- `WHISPER_MODEL=base` (optional local speech-to-text model)

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

## Voice commands

1. Allow microphone access in Chrome or Edge.
2. Click **Start voice input**, speak, then click **Stop recording**.
3. Audio is sent to the local backend and transcribed with faster-whisper.
4. The transcript is passed to Ollama for intent understanding and execution.

The first Whisper run downloads the selected model. Audio transcription is local; no browser cloud speech recognition is used.

## CLI

```powershell
python -m desktop_agent "Open Notepad"
```

## API

- `GET /health` — health check
- `GET /api/apps` — supported application allowlist
- `GET /api/ollama/status` — Ollama and model status
- `POST /api/commands` — JSON: `{"text":"Open Notepad","use_ollama":true}`
- `POST /api/voice/transcribe` — multipart upload with field name `audio`

## Safety and current scope

- The server binds to localhost by default.
- Only allowlisted apps can be launched.
- Commands use argument arrays and `shell=False`.
- This version does not yet click arbitrary UI controls, type into other applications, or execute multi-step workflows. Those require a separate permission and verification layer.

## Tests

```powershell
pip install -e ".[dev]"
pytest -q
```

## Roadmap

1. Desktop screenshots and visual inspection
2. Mouse and keyboard actions with explicit confirmation
3. Multi-step task planning and execution verification
4. Session memory, audit logs, retries, and recovery
5. Wake-word and push-to-talk support
