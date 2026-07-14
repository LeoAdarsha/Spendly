## 1. Overview

Implement user registration for Spendly, replacing the GET-only stub route
in `app.py` with full `POST` handling: form validation, password hashing,
account creation, and session-based login on success.

This step lets a new user create an account and land in the app as an
authenticated session. Login (`POST /login`) for *existing* users is a
separate, later step — out of scope here.

---

## 2. Depends on

`01-database-setup` — requires a working `users` table and `get_db()`.

---

## 3. Routes

- `GET /register` — existing, renders `register.html` (unchanged)
- `POST /register` — new: validate input, create account, log the user in,
  redirect

Out of scope:
- `POST /login` (separate future step)
- `/logout` (Step 3 placeholder, unchanged)

---

## 4. Database Schema

No changes. Reuses the existing `users` table from `01-database-setup`:

| Column | Type | Constraints |
| --- | --- | --- |
| id | INTEGER | Primary key, autoincrement |
| name | TEXT | Not null |
| email | TEXT | Unique, not null |
| password_hash | TEXT | Not null |
| created_at | TEXT | Default datetime('now') |

---

## 5. Session Setup

- `app.py` must set `app.secret_key` (required for Flask's signed session
  cookie) before any route uses `session`
- For local dev, a fixed string constant is fine (e.g.
  `os.environ.get("SECRET_KEY", "dev-secret-key")`) — no `.env`/config
  system needed for this step
- On successful registration, store the new user's id in the session:
  `session["user_id"] = user_id`

---

## 6. Route Logic — `POST /register`

- Read `name`, `email`, `password` from `request.form`
- Validate:
    - all three fields are present and non-empty (after `.strip()`)
    - email is not already registered (`SELECT` by email before insert)
- On validation failure: re-render `register.html` with
  `error=<message>` and `HTTP 400`
- On success:
    - hash the password with `generate_password_hash`
    - `INSERT` into `users` (`name`, `email`, `password_hash`)
    - set `session["user_id"]` to the new row's id
    - redirect to `/profile` (Step 4 placeholder — route exists, body is a
      placeholder string; redirecting there is fine)

---

## 7. Changes to `app.py`

- Import:
    - `request`, `redirect`, `url_for`, `session` from `flask`
    - `generate_password_hash` from `werkzeug.security`
- Set `app.secret_key`
- Change the `/register` route decorator to `methods=["GET", "POST"]`
- Branch on `request.method` inside the view to keep the existing `GET`
  render behavior intact — `GET` must keep returning
  `render_template("register.html")` unchanged

---

## 8. Files to Change

- `app.py` — add `POST` handling, session setup, imports

---

## 9. Files to Create

- None

---

## 10. Dependencies

- No new pip packages
- Use:
    - `flask.session` (built-in)
    - `werkzeug.security.generate_password_hash` (already installed, used
      in `seed_db()`)

---

## 11. Rules for Implementation

- Never store or log plaintext passwords
- Use parameterized queries only (no string formatting in SQL)
- Registration errors may be specific (e.g. "Email already registered")
  since the user is actively choosing that email — this is not the login
  path, so there's no user-enumeration concern
- Reuse the existing `auth-error`, `form-input`, `btn-submit` CSS classes
  and the `{% if error %}` block already present in `register.html` — no
  template changes needed
- Do not add `flash()` messaging or new template blocks; the `error`
  variable passed to `render_template` is sufficient

---

## 12. Expected Behavior

- Submitting `register.html` with a new name/email/password creates a
  user, hashes the password, sets `session["user_id"]`, and redirects to
  `/profile`
- Submitting `register.html` with an already-used email re-renders the
  form with an error and does not create a duplicate row
- Submitting `register.html` with a missing field re-renders the form with
  an error and does not touch the database
- `GET /register` behavior is byte-for-byte unchanged

---

## 13. Error Handling Expectations

- Missing/empty form fields → re-render with error, `HTTP 400`
- Duplicate email → re-render with error, `HTTP 400` (pre-check via
  `SELECT`, or catch the `UNIQUE` constraint violation)
- No unhandled exceptions/500s for any of the above cases

---

## 14. Definition of Done

- [ ]  `app.secret_key` is set
- [ ]  `POST /register` creates a user with a hashed password
- [ ]  `POST /register` rejects duplicate emails with a clear error
- [ ]  `POST /register` rejects missing fields with a clear error
- [ ]  Successful registration sets `session["user_id"]` and redirects to
      `/profile`
- [ ]  Existing `GET /register` behavior is unchanged
- [ ]  No plaintext passwords stored or logged
- [ ]  All queries use parameterized SQL
