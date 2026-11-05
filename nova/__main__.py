"""CLI entry point: python -m nova "Open Notepad"."""

import sys

from nova.actions.apps import launch_app
from nova.parser import parse_command


def main() -> int:
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        print('Usage: python -m nova "Open Notepad"')
        return 2

    intent = parse_command(text)
    if intent is None:
        print("Unsupported command. Try: Open Notepad, Launch Calculator, Open File Explorer.")
        return 2

    try:
        result = launch_app(intent.app_id)
        print(f"Successfully launched {result['app']}.")
        return 0
    except Exception as exc:
        print(f"Could not launch application: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
