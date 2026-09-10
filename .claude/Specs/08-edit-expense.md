# Spec: Edit Expense

## Overview
Step 8 turns the `/expenses/<int:id>/edit` placeholder into the first real
*update* path for expense data. Step 7 let a logged-in user create expense
rows; this step lets them correct one — change the amount, category, date, or
description of an expense they already own — and see the fix reflected
immediately on the Step 5 profile dashboard (Recent Transactions, Total
spent, Transactions count, and the category breakdown). It reuses Step 7's
validation rules and form styling wholesale, and adds the per-row **Edit**
link that makes each transaction on `/profile` actionable. Together with
delete (Step 9) it completes CRUD for expenses.

## Depends on
- **Step 1 — Database setup:** the `expenses` table and `get_db()` exist.
- **Step 3 — Login / Logout:** `session["user_id"]` gates protected routes;
  the same guard is reused here.
- **Step 5 — Backend routes for profile page:** `/profile` renders live data
  via `get_expenses_by_user()` / `get_category_totals()`, so an updated row
  shows its new values with no further work.
- **Step 7 — Add expense:** provides `parse_amount()`, the reuse of
  `parse_date_arg()`, the `CATEGORIES` import, the `add-expense.css` form
  styling this step reuses, and the `add_expense.html` form this step's
  template mirrors.

Steps 2, 4, and 6 are not required by this feature.

## Routes
- `GET /expenses/<int:id>/edit` — render the edit form pre-filled with the
  expense's current amount, category, date, and description — logged-in only
  (redirect to `/login` if not authenticated). The expense must belong to
  `session["user_id"]`; a missing id or one owned by another user returns
  `404`.
- `POST /expenses/<int:id>/edit` — validate the submitted fields (identical
  rules to Step 7); on success update that one row and redirect to `/profile`
  (302); on failure re-render the form with an error message and HTTP 400 —
  logged-in only (redirect to `/login`, update nothing, if not
  authenticated). A missing id or another user's id returns `404` and updates
  nothing.

The existing decorator `@app.route("/expenses/<int:id>/edit")` must become
`@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])` and the
placeholder string body is replaced with the real view. The route parameter
stays named `id`, matching the existing `edit_expense`/`delete_expense`
signatures.

## Database changes
No schema changes. The `expenses` table already has every needed column; the
edit never touches `id`, `user_id`, or `created_at`.

Two new helpers are added to `database/db.py`:

- `get_expense_by_id(expense_id, user_id)` — parameterised
  `SELECT * FROM expenses WHERE id = ? AND user_id = ?`, `fetchone()`, return
  the row or `None`, then `close()`. Ownership is enforced in the query, so
  the caller cannot accidentally load another user's row.
- `update_expense(expense_id, user_id, amount, category, date, description)` —
  parameterised
  `UPDATE expenses SET amount = ?, category = ?, date = ?, description = ?
  WHERE id = ? AND user_id = ?`, `commit()`, return `cursor.rowcount`, then
  `close()`. `user_id` in the `WHERE` is a second ownership guard; `rowcount`
  is `0` when nothing matched. `created_at` is deliberately not in the `SET`
  list. Mirrors the shape of the existing `create_expense()`.

The module docstring at the top of `database/db.py` gains a line for each of
`get_expense_by_id()` and `update_expense()`.

## Templates
- **Create:** `templates/edit_expense.html` — extends `base.html`, loads its
  own `static/css/edit-expense.css` in `{% block head %}` (a copy of
  `add-expense.css`, keeping the one-stylesheet-per-page pattern from Steps 6
  & 7). Mirrors `add_expense.html`, differing only in:
  - `{% block title %}Edit expense — Spendly{% endblock %}`,
  - header text: "Edit an expense" / "Update a transaction in your ledger",
  - `<form method="POST" action="{{ url_for('edit_expense', id=expense_id) }}">`,
  - submit button label **Save changes**,
  - all four fields pre-filled from `amount_value`, `category_value`,
    `date_value`, `description_value` (same variable names the view passes on
    Step 7's add form).
  - Cancel link (`.btn-ghost`) back to `{{ url_for('profile') }}`.
- **Modify:** `templates/profile.html` — in the Recent Transactions table
  (`.txn-table`), add a trailing **Actions** column: one `<th></th>` in the
  header and, per row, `<td class="txn-action"><a href="{{
  url_for('edit_expense', id=e.id) }}">Edit</a></td>`. This requires
  `build_recent_expenses()` to include the row `id` (see **Files to
  change**). No other structural change; the empty-state branches are
  untouched.
- **Modify:** `static/css/profile.css` — one small rule block for
  `.txn-action` / `.txn-action a` (right-aligned cell, link uses
  `var(--color-accent)` or the existing link token, no underline until
  hover). No other change.

## Files to change
- `app.py`
  - Add `get_expense_by_id` and `update_expense` to the
    `from database.db import (…)` block. Add `abort` to the
    `from flask import (…)` block.
  - Change the `/expenses/<int:id>/edit` decorator to
    `methods=["GET", "POST"]` and replace the placeholder body with the real
    view:
    - session guard → `redirect(url_for("login"))` if
      `session.get("user_id") is None`;
    - `expense = get_expense_by_id(id, session["user_id"])`; if `None`,
      `abort(404)`;
    - on `GET`: render `edit_expense.html` with `expense_id=id`,
      `categories=CATEGORIES`, and the four `*_value` fields taken from
      `expense`;
    - on `POST`: read `amount`/`category`/`date`/`description` from
      `request.form`, validate with the **same** logic as `add_expense`
      (`parse_amount`, `category in CATEGORIES`, `parse_date_arg`,
      `description.strip()` with a 200-char cap); on any failure re-render
      `edit_expense.html` with a specific `error=` and status `400`, echoing
      the submitted values (an unparseable date falls back to the expense's
      stored `date`); on success call
      `update_expense(id, session["user_id"], amount, category, date,
      description or None)` and `redirect(url_for("profile"))` (302).
  - `build_recent_expenses()` — add `"id": row["id"]` to each emitted dict so
    the profile template can build the Edit link. No other change to the
    builder or its docstring contract beyond noting the new key.
- `database/db.py`
  - Add `get_expense_by_id()` and `update_expense()` (see **Database
    changes**) and update the module docstring.
- `templates/profile.html`
  - Add the Actions column + per-row Edit link described above.
- `static/css/profile.css`
  - Add the `.txn-action` rule described above.

## Files to create
- `templates/edit_expense.html` — the edit form (see **Templates**).
- `static/css/edit-expense.css` — page-specific styling for the edit form; a
  copy of `static/css/add-expense.css` with only its header comment changed.
  All colours via `var(--…)` tokens from `static/css/style.css`.

## New dependencies
No new dependencies. `abort` comes from `flask`, already a dependency;
`datetime` (stdlib) is already imported in `app.py`.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only.
- Parameterised queries only — `get_expense_by_id()` and `update_expense()`
  pass the id, the user id, and every column value as SQL parameters; never
  string-format a value into the query text.
- Passwords hashed with werkzeug — unchanged; this step touches no auth code
  beyond the existing `session.get("user_id")` guard.
- Use CSS variables from `:root` in `static/css/style.css` — never hardcode
  hex values. No inline styles.
- All templates extend `base.html`.
- **Ownership is enforced server-side, in SQL.** Every read and write is
  scoped `WHERE id = ? AND user_id = ?` with `session["user_id"]`. The
  expense id comes only from the URL; the user id comes only from the
  session. A logged-in user who requests or POSTs to another user's expense
  id — or a non-existent id — gets `404` and no row is written. Never read
  `user_id` (or the target `id`) from the form body.
- **Validation is identical to Step 7 and must be shared, not duplicated** —
  reuse `parse_amount()` and `parse_date_arg()`:
  - `amount` — required; must parse as a number and be strictly `> 0`. Empty,
    non-numeric, `0`, and negative values are rejected.
  - `category` — required; must be exactly one of `database.db.CATEGORIES`.
  - `date` — required; must parse as `YYYY-MM-DD` via `parse_date_arg()`. No
    future-date check in this step.
  - `description` — optional; `.strip()`; store `None` when blank; reject if
    it exceeds 200 characters.
- On any validation failure: re-render `edit_expense.html` with a specific
  `error=` message and HTTP `400`, echoing the user's submitted values back
  into the form (invalid `date_value` falls back to the expense's stored
  date). No `flash()` — pass `error` to `render_template`, matching the auth
  and add-expense routes.
- On success: exactly the targeted row is updated (`amount`, `category`,
  `date`, `description`); `id`, `user_id`, and `created_at` are left
  untouched; then `redirect(url_for("profile"))` (302). No row is inserted or
  deleted — the total count of `expenses` rows is unchanged.
- Both `GET` and `POST` require a logged-in session; an unauthenticated
  request returns `redirect(url_for("login"))` (302) and must not update.
- Amount is stored as a plain number in the `REAL` column — no `₹` symbol in
  the database. Currency formatting stays in `format_currency()` at render
  time.
- The Recent Transactions Edit link must be built with
  `url_for('edit_expense', id=e.id)` — never a hand-assembled URL string.
- Importing `app` under pytest must still not seed the real
  `expense_tracker.db` — the `if "pytest" not in sys.modules` guard around
  `init_db()` / `seed_db()` is unchanged.

## Definition of done
- [ ] `GET /expenses/<id>/edit` while logged out redirects to `/login`
      (302).
- [ ] `GET /expenses/<id>/edit` for an expense owned by the logged-in user
      returns `200` and shows Amount, Category, Date, and Description fields
      pre-filled with that expense's current values.
- [ ] The Category `<select>` shows the expense's current category as the
      `selected` option.
- [ ] `GET /expenses/<id>/edit` for an id that belongs to a different user
      returns `404`.
- [ ] `GET /expenses/999999/edit` (no such row) returns `404`.
- [ ] Submitting valid changes (e.g. amount `99.00`, category `Bills`,
      today's date, description "Fixed") redirects to `/profile` (302) and
      the row now shows the new values in Recent Transactions, Total spent,
      Transactions count, and the Spending by Category breakdown.
- [ ] After a successful edit, that row's `created_at` in the database is
      unchanged and no new row was inserted (total `expenses` row count is
      the same as before).
- [ ] `POST /expenses/<id>/edit` with a blank amount re-renders the form with
      a visible error, returns `400`, and leaves the row unchanged in the
      database.
- [ ] `POST` with amount `0`, `-5`, or `abc` re-renders with an error
      (`400`); the row is unchanged.
- [ ] `POST` with `category=NotACategory` re-renders with an error (`400`);
      the row is unchanged.
- [ ] `POST` with `date=banana` or a blank date re-renders with an error
      (`400`); the row is unchanged.
- [ ] `POST` with a description longer than 200 characters re-renders with an
      error (`400`); the row is unchanged.
- [ ] After a validation error, the values the user did enter are still
      populated in the re-rendered form.
- [ ] `POST /expenses/<id>/edit` targeting another user's expense returns
      `404` and does not modify that row.
- [ ] `POST /expenses/<id>/edit` while logged out redirects to `/login`
      (302) and modifies nothing.
- [ ] A `user_id` field smuggled into the POST body is ignored — the row
      stays owned by its original `session["user_id"]`.
- [ ] Every row in Recent Transactions on `/profile` has an **Edit** link
      that opens `GET /expenses/<that row's id>/edit`.
- [ ] `grep` finds no `#` hex colour literals in `templates/edit_expense.html`,
      `static/css/edit-expense.css`, or the new `static/css/profile.css` rule —
      only `var(--…)` tokens.
- [ ] A stored amount stays a number (e.g. `99.0` in the DB), with the `₹`
      symbol added only at display time.
