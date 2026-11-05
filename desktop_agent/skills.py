"""Built-in, inspectable agent skills (procedural guidance, not executable code)."""

from __future__ import annotations

SKILLS = {
    "open_app": {
        "name": "Open an application",
        "description": "Open one of the supported Windows applications by natural-language request.",
        "instructions": "Resolve the requested app to the supported application allowlist. Use launch_app only for open requests. Use close_app only for explicit close requests and require approval. Never construct shell commands or force-close the Windows shell.",
        "examples": ["Open Notepad", "Start Calculator", "Launch VS Code", "Close WhatsApp"],
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
        "instructions": "For read-only awareness, use get_active_window or list_open_windows. To inspect a window's accessible controls, use get_window_controls with its title; it returns names and types only, never field values. For a button click by accessible name, resolve an exact unique visible enabled Button, show the window and button names, then require the one-time confirmation endpoint. Never click ambiguous controls. For other interactions, use a fresh screenshot, create a bounded plan, show every step, and require explicit approval. Never enter passwords, perform payments, delete data, or change security settings.",
        "examples": ["Click the visible Settings button", "Scroll down this page"],
    },
    "browser_tabs": {
        "name": "Manage browser tabs",
        "description": "Open a tab in the focused supported browser or close the current tab after approval.",
        "instructions": "Use open_new_tab only when the user explicitly requests a new tab and a supported browser is foreground. Use close_current_tab only for an explicit close request and wait for approval through /api/commands/confirm. Never switch focus to a browser or close a tab in a non-browser window.",
        "examples": ["Open a new tab", "Close this tab"],
    },
    "system_status": {
        "name": "Check system status",
        "description": "Read basic operating system, CPU, Python, hostname and disk information.",
        "instructions": "Use get_system_status for read-only diagnostics. Do not claim to run arbitrary PowerShell, CMD, registry, service, shutdown, restart, or security commands; those are not exposed.",
        "examples": ["Show my system information", "How much disk space is free?", "How many CPU cores do I have?"],
    },
    "file_management": {
        "name": "Read and write workspace files",
        "description": "Read UTF-8 text files and stage new or edited files inside the configured workspace.",
        "instructions": "Use read_file for UTF-8 text files. Use list_project_files to inspect source/config files and search_project to find literal text in a project. Use prepare_file_write to create or edit a file; it stages the change and returns a preview and one-time confirmation token. Show the target path, overwrite status and preview. Never claim a write is complete until the user confirms through POST /api/files/confirm-write. Folder creation also requires approval through POST /api/commands/confirm. Do not access secrets, credentials, browser profiles, or system files. Do not use shell commands for file operations.",
        "examples": ["Read README.md", "Create notes/todo.txt with these tasks", "Update config/settings.json"],
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
