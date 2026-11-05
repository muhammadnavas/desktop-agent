"""Built-in, inspectable agent skills (procedural guidance, not executable code)."""

from __future__ import annotations

SKILLS = {
    "open_app": {
        "name": "Open an application",
        "description": "Open one of the supported Windows applications by natural-language request.",
        "instructions": "Resolve the requested app to the supported application allowlist. Use the launch_app tool only. Never construct shell commands.",
        "examples": ["Open Notepad", "Start Calculator", "Launch VS Code"],
    },
    "code_autometa": {
        "name": "Start Code Autometa",
        "description": "Open the configured AI Browser Automation Agent project and start its development servers.",
        "instructions": "When the user explicitly says Code Autometa, use the fixed Code Autometa workflow. Do not invent project paths or claim the servers are healthy unless checked.",
        "examples": ["Alexa, Code Autometa", "Start Code Autometa project"],
    },
    "desktop_task": {
        "name": "Operate the visible desktop",
        "description": "Plan a bounded interaction with the current visible screen and request approval before execution.",
        "instructions": "For read-only awareness, use get_active_window or list_open_windows. For interactions, use a fresh screenshot, create a bounded plan, show every step, and require explicit approval. Never enter passwords, perform payments, delete data, or change security settings.",
        "examples": ["Click the visible Settings button", "Scroll down this page"],
    },
    "voice_command": {
        "name": "Handle voice commands",
        "description": "Convert a spoken command into the same validated command flow used for typed requests.",
        "instructions": "Treat transcription as untrusted user input. Route it through the normal command parser and registered tools.",
        "examples": ["Alexa, open File Explorer"],
    },
}


def list_skills() -> list[dict]:
    return [
        {"id": skill_id, "name": item["name"], "description": item["description"], "examples": item["examples"]}
        for skill_id, item in SKILLS.items()
    ]


def get_skill(skill_id: str) -> dict:
    skill = SKILLS.get(skill_id)
    if skill is None:
        raise KeyError(skill_id)
    return {"id": skill_id, **skill}
