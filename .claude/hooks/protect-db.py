#!/usr/bin/env python3
"""PreToolUse(Bash) hook — refuse shell commands that would delete or destroy
irreplaceable Spendly project files.

Registered in .claude/settings.json. Reads the hook payload as JSON on stdin.
Exit 2 blocks the tool call and feeds stderr back to Claude; exit 0 lets it
through.

Protected paths (none of these can be recovered from version control):
  * expense_tracker.db  — the SQLite database, gitignored, real data.
  * .env                — secrets / config, gitignored (.env.example and
                          friends are committed, so they are NOT protected).
  * migrations/          — schema history; wiping it desyncs every database.
"""

import json
import re
import sys

# --- What we protect -----------------------------------------------------------
# Each entry: (regex that spots the path in a command, human label for messages).
PROTECTED_TARGETS = [
    (re.compile(r"(expense_tracker|spendly)\.db\b", re.IGNORECASE),
     "the project database (expense_tracker.db)"),
    # .env, .env.local, .env.production ... but NOT .env.example/.sample/.template/.dist
    (re.compile(r"(?:^|[\s'\"=/])\.env(?:\.(?!example|sample|template|dist)[\w.-]+)?(?![\w.])",
                re.IGNORECASE),
     "the .env file (secrets, gitignored, unrecoverable)"),
    # the migrations/ directory or a file inside it
    (re.compile(r"(?:^|[\s'\"/])migrations(?:/|\b)", re.IGNORECASE),
     "the migrations/ directory (schema history)"),
]

# Destructive commands we never allow once a protected path is named.
# {t} is filled in with the matched target's label.
NAMED_DESTRUCTIVE = [
    (re.compile(r"\b(rm|unlink|shred|trash|trash-put|gio\s+trash)\b", re.IGNORECASE),
     "an rm / unlink / shred command targets {t}"),
    (re.compile(r"\bmv\b", re.IGNORECASE),
     "moving or renaming {t} is treated as deletion"),
    (re.compile(r">\s*['\"]?(?:[\w./-]*/)?(?:(?:expense_tracker|spendly)\.db|\.env(?:\.[\w.-]+)?)",
                re.IGNORECASE),
     "redirecting output over {t} would erase it"),
    (re.compile(r"\bfind\b.*(-delete\b|-exec\s+(rm|unlink|shred)\b)", re.IGNORECASE | re.DOTALL),
     "a `find ... -delete` / `-exec rm` could remove {t}"),
    (re.compile(r"\bdd\b.*\bof=\s*['\"]?(?:[\w./-]*/)?(?:(?:expense_tracker|spendly)\.db|\.env(?:\.[\w.-]+)?)",
                re.IGNORECASE),
     "`dd` writing over {t} would destroy it"),
]

# Bulk wipes that would sweep a protected path in without ever naming it.
BULK_DESTRUCTIVE = [
    (re.compile(r"\bgit\s+clean\b", re.IGNORECASE),
     "`git clean` removes gitignored files, and both expense_tracker.db and .env are gitignored"),
    (re.compile(r"\brm\b[^\n|;&]*\*(\.db|\.sqlite3?)\b", re.IGNORECASE),
     "an `rm *.db` glob would include the project database"),
    (re.compile(r"\brm\b(\s+-[A-Za-z]+)*\s+(\*|\.|\./|~|\$HOME|\$\{HOME\}|/)(\s|;|&|$)", re.IGNORECASE),
     "a wildcard / whole-directory `rm` would take protected files "
     "(expense_tracker.db, .env, migrations/) with it"),
]


def find_reason(cmd):
    for rx, msg in BULK_DESTRUCTIVE:
        if rx.search(cmd):
            return msg
    for target_rx, label in PROTECTED_TARGETS:
        if target_rx.search(cmd):
            for rx, msg in NAMED_DESTRUCTIVE:
                if rx.search(cmd):
                    return msg.format(t=label)
    return None


def main():
    raw = sys.stdin.read()
    try:
        cmd = json.loads(raw).get("tool_input", {}).get("command", "")
    except (ValueError, AttributeError):
        cmd = raw  # unparseable payload: scan whatever we got rather than trust it

    if not cmd:
        return 0

    reason = find_reason(cmd)
    if reason is None:
        return 0

    sys.stderr.write(
        "Blocked by .claude/hooks/protect-db.py - " + reason + ".\n"
        "Spendly protects expense_tracker.db, .env, and migrations/ from deletion.\n"
        "If you truly intend this: back it up first, then run the command in a\n"
        "plain terminal or temporarily remove the hook from .claude/settings.json.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
