# NOVA — Local Desktop Agent

NOVA is a local-first Windows desktop assistant. This first milestone implements a safe, working feature: launch a small allowlist of desktop applications using natural-language text commands.

## v0.1 feature

Try:
- `Open Notepad`
- `Launch Calculator`
- `Open File Explorer`
- `Start VS Code`

NOVA parses the request, maps it to an approved application, and launches it without using a shell.

## Requirements

- Windows 10/11
- Python 3.10+
- Optional: Visual Studio Code installed and its `code` command available on PATH

## Run

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn nova.api:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765 in your browser.

You can also use the CLI:

```powershell
python -m nova "Open Notepad"
```

## API

- `POST /api/commands` with JSON body `{"text": "Open Calculator"}`
- `GET /api/apps` lists supported applications.
- `GET /health` returns service status.

## Safety model

- Only explicitly allowlisted applications can be launched.
- Commands are launched with argument arrays and `shell=False`.
- NOVA does not execute arbitrary terminal commands.
- The API binds to localhost by default.
- This is an early prototype, not a general-purpose autonomous agent yet.

## Project structure

```text
nova-desktop-agent/
├── nova/
│   ├── actions/apps.py
│   ├── web/index.html
│   ├── parser.py
│   ├── api.py
│   └── __main__.py
├── tests/
├── requirements.txt
└── README.md
```

## Roadmap

1. Safe application launcher (current)
2. Desktop screenshots and UI inspection
3. Mouse and keyboard actions with confirmation
4. Task planning and step-by-step execution
5. Local LLM integration through Ollama
6. Memory, audit logs, recovery and voice input
