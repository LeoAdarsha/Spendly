# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

"Spendly" is a Flask-based expense tracker built as a step-by-step learning project. Many parts of the codebase are intentionally unimplemented placeholders — comments like `# Step 1 — Database Setup` and route bodies returning strings like `"Profile page — coming in Step 4"` mark work that hasn't been built yet. When asked to implement one of these steps, look for existing comments/docstrings near the placeholder first, since they describe the expected contract (function names, return shape, etc.) before you design your own.

## Commands

```bash
# Setup (venv already exists at ./venv, gitignored)
source venv/bin/activate
pip install -r requirements.txt

# Run the dev server (http://localhost:5001)
python app.py

# Run tests (pytest + pytest-flask are installed, but no tests/ directory exists yet)
pytest
```

There is no build step, linter, or frontend bundler configured — templates and static assets are served directly by Flask.

## Architecture

- **`app.py`** — single-file Flask app containing all routes. No blueprints; add new routes directly here.
- **`database/db.py`** — currently just a stub docstring. It is meant to hold `get_db()` (SQLite connection with `row_factory` and foreign keys enabled), `init_db()` (creates tables with `CREATE TABLE IF NOT EXISTS`), and `seed_db()` (sample data for dev). The SQLite file (`expense_tracker.db`) is gitignored and created at the project root.
- **`templates/`** — Jinja2 templates. `base.html` is the shared layout (navbar + footer) and defines blocks `title`, `head`, `content`, `scripts` for child templates to override via `{% extends "base.html" %}`.
- **`static/css/style.css`** — global design system (CSS custom properties for colors, fonts, spacing under `:root`) plus shared component styles (auth forms, buttons, etc.).
- **`static/css/landing.css`** — landing-page-specific styles, loaded in addition to `style.css` only on that page.
- **`static/js/main.js`** — currently an empty stub; add page behavior here as features are built.

## Current state / gaps to be aware of

- `login.html` and `register.html` render forms that `POST` to `/login` and `/register`, but `app.py` only defines `GET` handlers for those routes today — submitting either form will currently 405. Implementing auth means adding `methods=["GET", "POST"]` and the actual credential/DB logic.
- `logout`, `profile`, and the `/expenses/*` CRUD routes are placeholder strings, not real views — no expense data model exists yet.
- `database/__init__.py` is empty and `database/db.py` has no real code yet — nothing imports from `database` currently.
