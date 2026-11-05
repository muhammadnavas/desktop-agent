"""CLI entry point: python -m desktop_agent "Open Notepad".""" 

import sys

from desktop_agent.actions.apps import launch_app
from desktop_agent.ollama_client import OllamaError, understand_command
from desktop_agent.parser import parse_command


def main() -> int:
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        print('Usage: python -m desktop_agent "Open Notepad"')
        return 2

    try:
        parsed = understand_command(text)
        if parsed["action"] != "launch_app":
            print(parsed["response"] or "Unsupported action.")
            return 2
        app_id = parsed["app_id"]
    except OllamaError:
        intent = parse_command(text)
        if intent is None:
            print("Ollama is unavailable and the command was not recognized by the fallback parser.")
            return 2
        app_id = intent.app_id

    try:
        result = launch_app(app_id)
        print(f"Opening {result['app']}.")
        return 0
    except Exception as exc:
        print(f"Could not launch application: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
