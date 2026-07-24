# Spec: Profile Page

## Overview
Implement the logged-in user's profile page as a personal expense
dashboard. `GET /profile` currently returns the placeholder string
`"Profile page — coming in Step 4"`; this step replaces it with a real
view that reads the signed-in user's `session["user_id"]`, loads their
row from the `users` table plus a summary of their `expenses`, and
renders it in a new `profile.html` template. This is the first page in
the app that requires an authenticated session to view, so it also
introduces the project's first login-required route guard — a pattern
the upcoming `/expenses/*` CRUD routes (Steps 7–9) will reuse. It's also
the first place the app reads from the `expenses` table (seeded in
`01-database-setup`), ahead of full CRUD support.

## Depends on
`03-login-and-logout` — requires a real login/logout flow so
`session["user_id"]` is populated for a signed-in user and cleared on
sign-out. Also depends on `01-database-setup` and `02-registration` for
the `users`/`expenses` tables and `get_db()`.

## Routes
- `GET /profile` — modify existing placeholder — logged-in only — loads
  the current user and their expenses from the database and renders
  `profile.html`; if no user is logged in, redirect to `/login`

## Database changes
No new tables or columns. Reuses the existing `users` and `expenses`
tables from `01-database-setup`.

Two new helpers needed in `database/db.py`:
- `get_user_by_id(user_id)` — mirrors the existing `get_user_by_email()`
  but looks up by primary key, using a parameterized
  `SELECT * FROM users WHERE id = ?`
- `get_expenses_by_user(user_id)` — `SELECT * FROM expenses WHERE
  user_id = ? ORDER BY date DESC, id DESC`
- `get_category_totals(user_id)` — `SELECT category, SUM(amount) AS
  total FROM expenses WHERE user_id = ? GROUP BY category ORDER BY
  total DESC`

## Templates
- **Create:** `templates/profile.html` — extends `base.html`; renders:
  - a header card with an avatar (initials), the user's `name`,
    `email`, and `created_at` ("Member since <Month Year>")
  - a 3-up stat row: total spent (sum of the user's expense amounts,
    formatted as `₹`-prefixed currency), transaction count, and top
    spending category (highest `SUM(amount)` category, or an em dash
    if the user has no expenses)
  - a "Recent Transactions" table (date, description, category badge,
    amount) showing the 5 most recent expenses, or an empty-state
    message if there are none
  - a "Spending by Category" breakdown: one row per category with a
    proportional bar (width relative to the highest category total)
    and its formatted amount, or an empty-state message if there are
    none
  - no form inputs needed for this step (editing profile fields and
    full expense CRUD are out of scope — see Steps 7–9)
- **Modify:** `templates/base.html` — add a "Profile" link next to
  "Sign out" in `.nav-links` when `session.get('user_id')` is truthy, so
  the new page is reachable from the navbar

## Files to change
- `app.py` — replace the `/profile` placeholder body with real logic:
  redirect to `/login` if `session.get("user_id")` is `None`, otherwise
  call `get_user_by_id()`, `get_expenses_by_user()`, and
  `get_category_totals()`, compute the stat/summary values, and render
  `profile.html` (import the new helpers from `database.db`)
- `database/db.py` — add `get_user_by_id()`, `get_expenses_by_user()`,
  and `get_category_totals()`
- `templates/base.html` — add the "Profile" nav link described above
- `static/css/style.css` — add dashboard component styles (header card,
  avatar, stat tiles, transactions table, category bars)

## Files to create
- `templates/profile.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (n/a for reads, but never select or
  render `password_hash` in the template)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `GET /profile` must not be reachable without a session — always check
  `session.get("user_id")` first and redirect to `/login` if absent,
  before touching the database
- Never render `password_hash` anywhere in `profile.html`, even
  indirectly (e.g. don't pass the raw `sqlite3.Row` to `{{ }}` without
  selecting specific fields if that would leak it)
- Currency values are formatted server-side in `app.py` (e.g.
  `₹{:,.2f}`), not with ad-hoc Jinja filters, so the display format
  stays consistent with the rest of the app

## Definition of done
- [x] Visiting `/profile` while logged out redirects to `/login`
- [x] Visiting `/profile` while logged in (e.g. as `demo@spendly.com` /
      `demo123`) renders `profile.html` with that user's name, email,
      and member-since date
- [x] The dashboard shows correct total spent, transaction count, and
      top category for the logged-in user's expenses
- [x] "Recent Transactions" lists up to 5 most recent expenses with
      date, description, category, and amount
- [x] "Spending by Category" shows one bar per category the user has
      spent in, proportional to the highest category total
- [x] The rendered profile page never contains the word "password_hash"
      or the actual password hash value in its HTML source
- [x] The navbar shows a "Profile" link when logged in and none when
      logged out
- [x] `GET /login`, `POST /login`, and `GET /logout` behavior are
      unchanged
- [x] All queries use parameterized SQL
