# Spec: Login and Logout

## Overview
Implement session-based authentication for existing users: `POST /login`
verifies credentials against the `users` table and starts a session, and
`/logout` clears that session. This is the counterpart to registration
(Step 2), completing the auth flow so a returning user can sign back in
and sign out. Downstream steps (profile, expense CRUD) depend on a real
logged-in session being available via `session["user_id"]`.

## Depends on
`02-registration` — requires the `users` table, `get_db()`,
`get_user_by_email()`, `app.secret_key`, and the `session["user_id"]`
convention already established by the registration flow.

## Routes
- `GET /login` — existing, renders `login.html` (unchanged)
- `POST /login` — new — public — validate credentials, start session,
  redirect to `/profile`
- `GET /logout` — new — logged-in — clear session, redirect to `/login`

## Database changes
No changes. Reuses the existing `users` table from `01-database-setup`
and the `get_user_by_email()` helper from `02-registration`:

| Column | Type | Constraints |
| --- | --- | --- |
| id | INTEGER | Primary key, autoincrement |
| name | TEXT | Not null |
| email | TEXT | Unique, not null |
| password_hash | TEXT | Not null |
| created_at | TEXT | Default datetime('now') |

## Templates
- **Create:** none
- **Modify:** none — `login.html` already posts to `/login` with
  `email`/`password` fields and renders `{% if error %}`; no template
  changes needed

## Files to change
- `app.py` — change `/login` route to `methods=["GET", "POST"]`, add
  `POST` credential-check logic; replace the `/logout` placeholder with
  real session-clearing logic
- `database/db.py` — no changes expected (reuses `get_user_by_email()`);
  confirm during implementation that no new helper is needed

## Files to create
None.

## New dependencies
No new dependencies. Uses `werkzeug.security.check_password_hash`
(already available since `generate_password_hash` is in use) and
`flask.session` (already wired up in Step 2).

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug — use `check_password_hash` to verify,
  never compare plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- On failed login, use a single generic error (e.g. "Invalid email or
  password") for both "no such user" and "wrong password" cases — unlike
  registration, this path must not reveal whether an email is registered
  (user-enumeration concern)
- `POST /login` failure re-renders `login.html` with `error=<message>`
  and `HTTP 401`; it must not touch the database beyond the lookup
- `GET /logout` must clear the session (e.g. `session.clear()` or
  `session.pop("user_id", None)`) and redirect to `/login`, regardless of
  whether a session existed
- `GET /login` behavior must remain byte-for-byte unchanged

## Definition of done
- [ ] `POST /login` with a correct email/password sets
      `session["user_id"]` and redirects to `/profile`
- [ ] `POST /login` with a wrong password re-renders `login.html` with a
      generic error and `HTTP 401`, without creating or modifying any row
- [ ] `POST /login` with an unregistered email re-renders `login.html`
      with the same generic error and `HTTP 401`
- [ ] `GET /logout` clears the session and redirects to `/login`
- [ ] After `/logout`, visiting a page that reads `session["user_id"]`
      no longer shows the previous user's session
- [ ] Existing `GET /login` behavior is unchanged
- [ ] No plaintext passwords stored, logged, or compared
- [ ] All queries use parameterized SQL
