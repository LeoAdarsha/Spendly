#!/usr/bin/env python3
"""PostToolUse(Write|Edit) hook — format Python files with black after Claude edits them.

Registered in .claude/settings.json. Reads the hook payload as JSON on stdin. If the
written / edited path is a .py file, runs black on it (the copy in ./venv if present,
otherwise whatever `black` is on PATH).

Always exits 0 so a formatting hiccup never blocks an edit. If black itself reports an
error (for example the file has a syntax error it cannot parse) that line is surfaced
to the user via `systemMessage`; a clean run is silent.
"""

import json
import os
import subprocess
import sys


def find_black():
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if not root:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    venv_black = os.path.join(root, "venv", "bin", "black")
    return venv_black if os.path.exists(venv_black) else "black"


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0

    path = (
        payload.get("tool_input", {}).get("file_path")
        or payload.get("tool_response", {}).get("filePath")
        or ""
    )
    if not path.endswith(".py") or not os.path.isfile(path):
        return 0

    try:
        proc = subprocess.run(
            [find_black(), "-q", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"systemMessage": f"black hook could not run: {exc}"}))
        return 0

    if proc.returncode != 0 and proc.stderr.strip():
        last = proc.stderr.strip().splitlines()[-1]
        print(
            json.dumps(
                {
                    "systemMessage": f"black could not format {os.path.basename(path)}: {last}"
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
