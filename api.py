"""Local FastAPI interface for NOVA."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from nova.actions.apps import launch_app, supported_apps
from nova.parser import parse_command

app = FastAPI(
    title="NOVA Desktop Agent",
    version="0.1.0",
    description="Local-first desktop assistant prototype.",
)

INDEX_FILE = Path(__file__).parent / "web" / "index.html"


class CommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@app.get("/")
def home():
    return FileResponse(INDEX_FILE)


@app.get("/health")
def health():
    return {"status": "ok", "name": "NOVA", "version": "0.1.0"}


@app.get("/api/apps")
def get_apps():
    return {"apps": supported_apps()}


@app.post("/api/commands")
def execute_command(request: CommandRequest):
    intent = parse_command(request.text)
    if intent is None:
        raise HTTPException(
            status_code=422,
            detail="I couldn't identify a supported app-launch command. Try 'Open Notepad'.",
        )

    try:
        result = launch_app(intent.app_id)
        return {"success": True, "message": f"Opened {result['app']}.", "result": result}
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Windows could not launch the app: {exc}") from exc
