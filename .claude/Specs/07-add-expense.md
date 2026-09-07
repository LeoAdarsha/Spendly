# Spec: Add Expense

## Overview
Step 7 turns the `/expenses/add` placeholder into the first real *write* path
for expense data. Until now the only rows a user could create were their own
account (Step 2) and the dev seed data; every expense on the profile
dashboard came from `seed_db()`. This step adds a `GET` form and a validated
`POST` handler so a logged-in user can record a new expense (amount,
category, date, optional description) and immediately see it reflected in the
Step 5 profile dashboard — Recent Transactions, Total spent, and the category
breakdown. It is the foundation for edit (Step 8) and delete (Step 9).

## Depends on
- **Step 1 — Database setup:** the `expenses` table and `get_db()` exist.
- **Step 2 — Registration:** users exist and `session["user_id"]` is set on
  sign-up.
- **Step 3 — Login / Logout:** `session["user_id"]` gates protected routes;
  the same guard is reused here.
- **Step 5 — Backend routes for profile page:** `/profile` renders live data
  via `get_expenses_by_user()` / `get_category_totals()`, so a newly inserted
  row shows up with no further work.

Steps 4 and 6 are not required by this feature.

## Routes
- `GET /expenses/add` — render the add-expense form with an empty amount, an
  unselected category, the date pre-filled to today, and an empty
  description — logged-in only (redirect to `/login` if not authenticated).
- `POST /expenses/add` — validate the submitted fields; on success insert one
  row into `expenses` for `session["user_id"]` and redirect to `/profile`
  (302); on failure re-render the form with an error message and HTTP 400 —
  logged-in only (redirect to `/login`, insert nothing, if not
  authenticated).

The existing decorator `@app.route("/expenses/add")` must become
`@app.route("/expenses/add", methods=["GET", "POST"])` and the placeholder
string body is replaced with the real view.

## Database changes
No schema changes. The `expenses` table already has every needed column
(`user_id`, `amount`, `category`, `date`, `description`, `created_at` with its
`datetime('now')` default).

One new helper is added to `database/db.py`:

- `create_expense(user_id, amount, category, date, description=None)` —
  parameterised `INSERT INTO expenses (user_id, amount, category, date,
  description) VALUES (?, ?, ?, ?, ?)`, `commit()`, return `cursor.lastrowid`,
  then `close()`. Mirrors the existing `create_user()` exactly in shape.

The module docstring at the top of `database/db.py` gains a line for
`create_expense()`.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`, loads
  `static/css/add-expense.css` in `{% block head %}`. Contains:
  - a page header (title + one-line subtitle),
  - an `{% if error %}` banner (same role as the auth pages' error block),
  - `<form method="POST" action="{{ url_for('add_expense') }}">` with:
    - **Amount** — `<input type="number" name="amount" step="0.01"
      min="0.01" required>`, echoing `amount_value`.
    - **Category** — `<select name="category" required>` with a disabled
      placeholder option, then one `<option>` per entry in `categories`
      (passed from the view as `database.db.CATEGORIES`), marking
      `category_value` as `selected`.
    - **Date** — `<input type="date" name="date" required>`, value =
      `date_value`.
    - **Description** — `<input type="text" name="description"
      maxlength="200">` (optional), echoing `description_value`.
    - an **Add expense** submit button (`.btn-submit`).
    - a **Cancel** link (`.btn-ghost`) back to `{{ url_for('profile') }}`.
  - Reuses `.form-group`, `.form-input`, `.btn-submit`, `.btn-ghost` from
    `static/css/style.css`; `.form-input` is applied to the `<select>` too.
- **Modify:** `templates/profile.html` — add one **Add expense**
  `.btn-primary` link (`href="{{ url_for('add_expense') }}"`) to the
  `.profile-header-card`, so the feature is reachable from the dashboard. No
  other structural change. (Adding it to the shared `base.html` navbar is
  explicitly out of scope for this step.)

## Files to change
- `app.py`
  - Add `create_expense` and `CATEGORIES` to the `from database.db import (…)`
    block.
  - Change the `/expenses/add` decorator to `methods=["GET", "POST"]` and
    replace the placeholder body with the real view: session guard → on `GET`
    render the form (date defaulted to `datetime.now().strftime("%Y-%m-%d")`)
    → on `POST` validate, then either `create_expense(...)` +
    `redirect(url_for("profile"))` or re-render with `error=` and status
    `400`.
  - Add a small module-level `parse_amount(raw)` helper near the other
    formatting/parsing helpers: returns a positive `float` or `None`
    (`float()` in a `try/except (TypeError, ValueError)`, then `None` unless
    `> 0`). Reuse the existing `parse_date_arg()` for the date field.
- `database/db.py`
  - Add `create_expense()` (see **Database changes**) and update the module
    docstring.
- `templates/profile.html`
  - Add the **Add expense** CTA link described above.
- `static/css/profile.css`
  - One rule to right-align the new header CTA within `.profile-header-card`
    (e.g. a `.profile-header-action { margin-left: auto; }` class on the
    link). No other change.

## Files to create
- `templates/add_expense.html` — the add-expense form (see **Templates**).
- `static/css/add-expense.css` — page-specific styling: a centered page
  wrapper, the form card, the error banner, `<select>` appearance, and a
  responsive row that puts Amount and Date side by side on wide screens and
  stacks them under 600px. All colours via `var(--…)` tokens from
  `static/css/style.css`.

## New dependencies
No new dependencies. `datetime` (stdlib) is already imported in `app.py`.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only.
- Parameterised queries only — `create_expense()` passes all five values as
  SQL parameters; never string-format a value into the query text.
- Passwords hashed with werkzeug — unchanged; this step touches no auth code
  beyond the existing `session.get("user_id")` guard.
- Use CSS variables from `:root` in `static/css/style.css` — never hardcode
  hex values. No inline styles.
- All templates extend `base.html`.
- **Server-side validation is authoritative** — the browser's `required` /
  `min` / `type` attributes are convenience only. Every rule below must be
  enforced in the view:
  - `amount` — required; must parse as a number and be strictly `> 0`. Empty,
    non-numeric, `0`, and negative values are rejected.
  - `category` — required; must be exactly one of `database.db.CATEGORIES`. A
    hand-crafted POST with any other value is rejected, not stored.
  - `date` — required; must parse as `YYYY-MM-DD` via `parse_date_arg()`
    (which normalises and zero-pads). Junk is rejected. No future-date check
    in this step.
  - `description` — optional; `.strip()`; store `None` when blank. If it
    exceeds 200 characters, reject with an error.
- On any validation failure: re-render `add_expense.html` with a specific
  `error=` message and HTTP `400`, and echo the user's submitted values back
  into the form (valid `date_value` falls back to today if the submitted date
  did not parse). No `flash()` — pass `error` to `render_template`, matching
  the auth routes.
- On success: exactly one row is inserted, then `redirect(url_for("profile"))`
  (302).
- The new expense is always owned by `session["user_id"]`. Never read a
  `user_id` from the form body.
- Amount is stored as a plain number in the `REAL` column — no `₹` symbol in
  the database. Currency formatting stays in `format_currency()` at render
  time.
- Both `GET` and `POST` require a logged-in session; an unauthenticated
  request returns `redirect(url_for("login"))` (302) and must not insert.
- Importing `app` under pytest must still not seed the real
  `expense_tracker.db` — the `if "pytest" not in sys.modules` guard around
  `init_db()` / `seed_db()` is unchanged.

## Definition of done
- [ ] `GET /expenses/add` while logged out redirects to `/login` (302).
- [ ] `GET /expenses/add` while logged in returns `200` and shows Amount,
      Category, Date, and Description fields.
- [ ] The Category `<select>` lists exactly the seven `CATEGORIES` values
      (`Food, Transport, Bills, Health, Entertainment, Shopping, Other`).
- [ ] On a fresh `GET`, the Date field is pre-filled with today's date.
- [ ] Submitting a valid expense (e.g. amount `42.50`, category `Food`,
      today's date, description "Lunch") redirects to `/profile` (302) and
      inserts exactly one row into `expenses` for the logged-in user.
- [ ] That expense then appears on `/profile`: as the newest row in Recent
      Transactions, added into `Total spent`, counted in `Transactions`, and
      included in the Spending by Category breakdown.
- [ ] `POST /expenses/add` with a blank amount re-renders the form with a
      visible error, returns `400`, and inserts nothing.
- [ ] `POST /expenses/add` with amount `0`, `-5`, or `abc` re-renders with an
      error (`400`); nothing is inserted.
- [ ] `POST /expenses/add` with `category=NotACategory` re-renders with an
      error (`400`); nothing is inserted.
- [ ] `POST /expenses/add` with `date=banana` or a blank date re-renders with
      an error (`400`); nothing is inserted.
- [ ] After a validation error, the values the user did enter are still
      populated in the re-rendered form.
- [ ] `POST /expenses/add` while logged out redirects to `/login` (302) and
      inserts nothing.
- [ ] A `user_id` field smuggled into the POST body is ignored — the row is
      stored against `session["user_id"]`.
- [ ] An **Add expense** link on `/profile` navigates to `GET
      /expenses/add`.
- [ ] `grep` finds no `#` hex colour literals in `templates/add_expense.html`
      or `static/css/add-expense.css` — only `var(--…)` tokens.
- [ ] A stored amount is a number (e.g. `42.5` in the DB), with the `₹`
      symbol added only at display time.
