# Spec: Profile Page Backend Routes

## Overview
Step 4 built the full profile layout against hardcoded Python constants so the
design could be validated before any queries existed. This step deletes those
constants and wires `/profile` to the real database: the signed-in user's row,
their expenses, and their per-category totals. The rendered contract stays
identical — `profile.html` and the navbar keep receiving exactly the same
variable names and shapes — so the page should look the same for a user whose
data matches the old sample set, and correct for everyone else. This is the last
read-only step before expense CRUD (Steps 7–9) starts writing rows.

## Depends on
- `01-database-setup` — `users`/`expenses` tables, `get_db()`, `seed_db()`
- `02-registration` — `app.secret_key`, the `session["user_id"]` convention
- `03-login-and-logout` — a real session to read `user_id` from
- `04-profile-page` — `templates/profile.html`, `static/css/profile.css`, and the
  context shape this step must keep feeding

## Routes
No new routes. One existing route changes behaviour:

- `GET /profile` — unchanged path and access level (logged-in; redirects to
  `/login` when `session["user_id"]` is absent) — the view body now queries the
  database instead of reading module-level constants.

The `@app.context_processor` (`inject_current_user`) is not a route but changes
in the same way: `current_user_name` comes from the user's row, not from
`PROFILE_USER`.

## Database changes
No database changes. Verified against `database/db.py`: the `users` and
`expenses` tables already carry every column this step reads, and all three
helper functions this step needs already exist and use parameterised queries:

- `get_user_by_id(user_id)` — returns the user row (`name`, `email`, `created_at`)
- `get_expenses_by_user(user_id)` — all expense rows, `ORDER BY date DESC, id DESC`
- `get_category_totals(user_id)` — rows of `(category, total)`, `ORDER BY total DESC`

No new helper is expected. If implementation reveals one is genuinely needed, add
it to `database/db.py` following the existing style (open with `get_db()`,
parameterised SQL, `conn.close()` before returning).

## Templates
- **Create:** none
- **Modify:** none. `templates/profile.html` already renders every variable this
  step supplies and already has `{% if recent_expenses %}` / `{% if categories %}`
  empty-state branches; `templates/base.html` already reads `current_user_name`.
  If a template edit looks necessary, the view is producing the wrong shape —
  fix the view instead.

## Files to change
- `app.py`
  - Delete the `PROFILE_USER`, `PROFILE_TRANSACTIONS`, and
    `PROFILE_CATEGORY_TOTALS` constants and the Step 4 comments above them
  - Keep `CATEGORY_TONE`, `RECENT_LIMIT`, and `format_currency()`
  - Import `get_user_by_id`, `get_expenses_by_user`, `get_category_totals` from
    `database.db`; import `datetime` for date formatting
  - Rewrite `inject_current_user()` and the `profile()` view against the database
  - Add small module-level date-formatting helpers rather than inlining
    `strptime`/`strftime` calls in the view

## Files to create
None.

## New dependencies
No new dependencies. Uses `sqlite3` via the existing helpers and `datetime` from
the standard library.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` through `database/db.py` helpers only
- Parameterised queries only — never string-format SQL
- Passwords hashed with werkzeug — no auth changes in this step; do not read,
  log, or pass `password_hash` into any template context
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles — category bar widths keep using the
  `category-bar-fill--<step>` classes in `static/css/profile.css`, which exist
  only in 5% increments from `0` to `100`, so `percent_step` must round to a
  multiple of 5 in that range
- Keep the auth guard first in the view: `session.get("user_id")` absent →
  `redirect(url_for("login"))`
- **Stale session:** if `session["user_id"]` is set but `get_user_by_id()` returns
  `None` (e.g. the database file was recreated), clear the session and redirect
  to `/login` rather than raising. `inject_current_user()` must do the same
  defensively — return `{"current_user_name": None}` instead of crashing, since
  it runs for every template render including error pages
- **No behavioural drift in the template contract.** The view must still pass:
  `name`, `email`, `member_since`, `initials`, `total_spent`,
  `transaction_count`, `top_category`, `recent_expenses`, `categories`
  - `recent_expenses` — list of dicts with `date`, `description`, `category`,
    `tone`, `amount`
  - `categories` — list of dicts with `category`, `amount`, `percent`,
    `percent_step`
- `total_spent` and `transaction_count` cover **all** of the user's expenses;
  only `recent_expenses` is truncated to `RECENT_LIMIT`
- `top_category` is the highest-total category, or `None` when the user has no
  expenses (the template already renders `—` for `None`)
- `percent` is each category's total as a share of the **highest** category
  total, so the top row is always 100 — matching Step 4's behaviour. Guard
  against division by zero when there are no expenses
- All money passes through `format_currency()`; never format currency inline
- `initials` is derived from the user's `name` — first letter of the first and
  last whitespace-separated words, uppercased; a single-word name yields one
  letter. Never assume the name has two words
- `member_since` comes from `users.created_at`, formatted `"%B %Y"` (e.g.
  "January 2025"). `created_at` is written by SQLite's `datetime('now')` as
  `"YYYY-MM-DD HH:MM:SS"`, but treat it as untrusted: if it is `NULL` or
  unparseable, fall back to something sensible rather than raising
- Expense `date` is stored as `YYYY-MM-DD` and must render as `"Apr 08, 2026"`
  (`"%b %d, %Y"`); an unparseable stored date must fall through as the raw string
  rather than crash the page
- `description` is nullable in the schema — render an empty string, not `None`
- `tone` comes from `CATEGORY_TONE.get(category, "neutral")` so an unexpected
  category value still renders a valid badge class
- Sort order comes from SQL (`get_expenses_by_user` is already date-descending,
  `get_category_totals` already total-descending) — do not re-sort in Python

## Definition of done
- [ ] Visiting `/profile` without being logged in still redirects to `/login`
- [ ] Logging in as `demo@spendly.com` / `demo123` and visiting `/profile`
      returns HTTP 200 and shows **"Demo User"** and **demo@spendly.com** in the
      header card — not "Nitish Singh"
- [ ] The navbar shows "Demo User", sourced from the database
- [ ] "Member since" shows the month and year the demo user row was created
- [ ] "Total spent" equals the sum of all 8 seeded expenses (₹278.54), and
      "Transactions" shows 8 — not 5
- [ ] "Top category" matches the highest-total seeded category (Bills)
- [ ] The Recent Transactions table shows exactly `RECENT_LIMIT` (5) rows, newest
      first by date, with dates formatted like "Apr 08, 2026"
- [ ] The Spending by Category section lists every category the demo user has
      expenses in, highest first, with the top row's bar at full width
- [ ] Registering a brand-new user and visiting `/profile` returns HTTP 200 and
      shows ₹0.00 total, 0 transactions, "—" as top category, and both
      empty-state messages ("No expenses logged yet." / "No spending data yet.")
      with no traceback
- [ ] Deleting `expense_tracker.db` while logged in, then reloading `/profile`,
      redirects to `/login` instead of raising a 500
- [ ] `grep -n "PROFILE_USER\|PROFILE_TRANSACTIONS\|PROFILE_CATEGORY_TOTALS" app.py`
      returns nothing
- [ ] `templates/profile.html` and `templates/base.html` are unchanged
      (`git diff --stat` shows only `app.py`)
- [ ] All queries use parameterised SQL; no ORM introduced