# Spec: Date Filter for Profile Page

## Overview
The `/profile` dashboard currently shows *every* expense a user has ever
logged — the summary stats, the Recent Transactions table, and the Spending
by Category breakdown are all computed over the user's full history. Step 6
adds a date-range filter so a logged-in user can narrow all three sections to
a chosen window (e.g. "this month" or "1–15 April"). The filter is driven by
two optional query-string parameters on the existing route, so a filtered
view is bookmarkable and shareable. This is the last read-only enhancement to
the profile page before Step 7 introduces expense creation.

## Depends on
- Step 1: Database setup (`expenses` table with a `date` column, `get_db()`)
- Step 2: Registration (users exist)
- Step 3: Login / Logout (`session["user_id"]` gates `/profile`)
- Step 4: Profile page UI (`templates/profile.html` renders all four sections)
- Step 5: Backend routes for profile page (`profile()` reads live data via
  `get_expenses_by_user()` and `get_category_totals()` in `database/db.py`,
  and the `build_*` transforms in `app.py`)

## Routes
No new routes. `GET /profile` is modified to read two optional query-string
parameters:

- `GET /profile?start=YYYY-MM-DD&end=YYYY-MM-DD` — render the dashboard
  restricted to expenses whose `date` falls in the inclusive range —
  logged-in only (unauthenticated users still redirect to `/login`)
  - Both parameters are optional and independent: `start` alone means "on or
    after", `end` alone means "on or before", neither means "all time"
    (unchanged behaviour).
  - A value that does not parse as `YYYY-MM-DD` is ignored — treated as if
    that parameter were absent — and the page still renders `200`.
  - `start` later than `end` is not an error: the query simply matches no
    rows and the empty states render.

## Database changes
No database changes. The `expenses.date` column already stores dates as
`YYYY-MM-DD` text, so an inclusive range filter is a lexicographic
`date >= ? AND date <= ?` comparison — no new columns, tables, or indexes.

Two existing helpers in `database/db.py` gain **optional, backward-compatible**
keyword parameters:

- `get_expenses_by_user(user_id, start=None, end=None)`
- `get_category_totals(user_id, start=None, end=None)`

When `start` / `end` are `None` the SQL and results are byte-for-byte what
they are today (Step 5 behaviour and tests must keep passing). When provided,
each adds a parameterised `AND date >= ?` / `AND date <= ?` clause.

## Templates
- **Create:** none.
- **Modify:** `templates/profile.html`
  - Add a filter bar directly below `.profile-header-card` and above
    `.stats-grid`: a `<form method="get" action="{{ url_for('profile') }}">`
    containing
    - a `Start` `<input type="date" name="start">` with a `<label for>`
    - an `End` `<input type="date" name="end">` with a `<label for>`
    - an `Apply` submit button
    - a `Clear` link pointing at `{{ url_for('profile') }}` (no query string),
      shown only when a filter is active
  - Both date inputs echo the currently-applied value via
    `value="{{ start_value }}"` / `value="{{ end_value }}"` so the form stays
    populated after submitting.
  - The two empty-state messages become range-aware: when `filter_active` is
    true and a section has no rows, show "No expenses in the selected date
    range." / "No spending data for the selected date range." instead of the
    existing "No expenses logged yet." / "No spending data yet."
  - No structural changes to the stats grid, table, or category list — they
    already render whatever rows the view hands them.

## Files to change
- `app.py`
  - `profile()` — read `request.args.get("start")` / `("end")`, validate each
    with a new module-level `parse_date_arg(raw)` helper (returns the
    normalised `YYYY-MM-DD` string or `None`), pass the validated values into
    `get_expenses_by_user()` and `get_category_totals()`, and pass to the
    template: `start_value`, `end_value` (validated strings or `""`) and
    `filter_active` (`True` when at least one bound is set).
  - Add `parse_date_arg(raw)` near the other formatting helpers. It shares the
    lenient `strptime` parsing with `format_date()` via a small `_parse_ymd()`
    helper so the "accept only `YYYY-MM-DD`, tolerate junk" contract lives in
    one place.
- `database/db.py`
  - `get_expenses_by_user()` — add `start=None, end=None`; build the `WHERE`
    clause and params list dynamically via a private `_date_range_sql()`
    helper; keep `ORDER BY date DESC, id DESC`. Wrap the query in
    `try/finally` so a failing `execute` cannot leak the connection.
  - `get_category_totals()` — add `start=None, end=None`; inject the same
    clauses before `GROUP BY`; keep `ORDER BY total DESC`; same `try/finally`.
- `templates/profile.html` — add the filter bar and the range-aware empty
  states described above.
- `static/css/profile.css` — styles for the filter bar (`.filter-bar` and its
  children): layout, inputs, and a responsive rule so the controls stack on
  narrow screens. The `Apply` button reuses `.btn-primary` and the `Clear`
  link reuses `.btn-ghost` from `static/css/style.css`.

## Files to create
None. (`tests/` and its files are added by the separate `/test-feature` step.)

## New dependencies
No new dependencies. `datetime` (stdlib) is already imported in `app.py`.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only.
- Parameterised queries only — the `start` / `end` bounds must be passed as
  SQL parameters, never string-formatted into the query text.
- Passwords hashed with werkzeug — unchanged; this step touches no auth code
  beyond the existing `session.get("user_id")` guard on `/profile`.
- Validate every incoming date with `datetime.strptime(raw, "%Y-%m-%d")`;
  anything that raises is treated as absent. Never pass an unvalidated string
  to the query helpers.
- The filter form must use `method="get"` and submit to
  `url_for("profile")` — the view performs no state change, and the filtered
  view must be reproducible from the URL alone.
- Echo only *validated* values back into the date inputs (a rejected
  `?start=banana` leaves that input empty).
- `get_expenses_by_user()` and `get_category_totals()` must return exactly
  today's output when called with no date arguments — Step 5's tests keep
  passing.
- `start` later than `end` must not raise — let the query return no rows. No
  flash message; the range-aware empty states carry the feedback.
- Use CSS variables from `:root` in `static/css/style.css` — never hardcode
  hex values.
- All templates extend `base.html`. No inline styles — the bar width classes
  precedent in `profile.css` shows the pattern; the filter bar needs none.
- The Recent Transactions cap (`RECENT_LIMIT = 5`) is unchanged — the filter
  narrows the underlying rows, the table still shows at most the newest five.
- Importing `app` must not seed the real `expense_tracker.db` when running
  under pytest — the startup `init_db()` / `seed_db()` block is guarded with
  `if "pytest" not in sys.modules`.

## Definition of done
- [ ] `GET /profile` with no query string renders the full dashboard exactly
      as before — for the seed user: total `₹278.54`, `8` transactions, top
      category `Bills`.
- [ ] A filter bar with `Start` and `End` date inputs and an `Apply` button
      appears above the summary stat cards.
- [ ] Submitting the form navigates to
      `GET /profile?start=YYYY-MM-DD&end=YYYY-MM-DD` (values visible in the
      address bar) and returns `200`.
- [ ] Setting the range to span the seed month (1st to 28th) shows all `8`
      seed transactions and the same totals as the unfiltered view.
- [ ] Narrowing to the first third of the seed month (days `01`–`10`) reduces
      the Recent Transactions rows, the `Total spent` figure, the
      `Transactions` count, and the Spending by Category breakdown to only the
      expenses in that window.
- [ ] `start` alone shows every expense on or after that date; `end` alone
      shows every expense on or before it.
- [ ] `GET /profile?start=2000-01-01&end=2000-12-31` returns `200` with
      `Total spent` `₹0.00`, `Transactions` `0`, and the range-aware
      empty-state text in both the transactions card and the category card.
- [ ] After applying a filter, both date inputs stay populated with the
      submitted values.
- [ ] The `Clear` link is visible only when a filter is active and returns to
      `/profile` with no query string, restoring the full dashboard.
- [ ] `GET /profile?start=banana` returns `200` and renders the full
      unfiltered dashboard (the bad value is ignored).
- [ ] `GET /profile?start=2026-12-31&end=2026-01-01` returns `200` with the
      empty-state view and no server error.
- [ ] Visiting `/profile?start=...` while logged out still redirects to
      `/login`.
- [ ] `grep` finds no `#` hex colour literals in `templates/profile.html` or
      the new rules in `static/css/profile.css` — only `var(--…)` tokens.
- [ ] `pytest tests/test_date_filter_profile.py` — all tests pass.
