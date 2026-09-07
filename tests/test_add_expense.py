"""Step 7 - Add Expense.

Behaviour under test, taken straight from ``.claude/Specs/07-add-expense.md``
(its Routes, Rules for implementation, and Definition of done sections). These
tests describe what the feature *should* do; they never reverse-engineer the
current implementation.

* ``/expenses/add`` serves a ``GET`` form and a validated ``POST`` handler.
  Both require a logged-in session: a logged-out request is redirected to
  ``/login`` (302) and a logged-out ``POST`` must not insert anything.
* ``GET`` (authenticated) returns 200 and renders Amount, Category, Date and
  Description fields. The Category ``<select>`` offers exactly the seven
  ``database.db.CATEGORIES`` values (Food, Transport, Bills, Health,
  Entertainment, Shopping, Other) and the Date field is pre-filled with today
  (``datetime.now().strftime("%Y-%m-%d")``); amount / category / description
  start empty.
* A valid ``POST`` inserts exactly one ``expenses`` row for
  ``session["user_id"]`` and redirects to ``/profile`` (302). The amount is
  stored as a plain number (no ``INR`` symbol); category / date / description
  are stored as submitted; a blank description is stored as NULL. The new row
  then shows up on ``/profile`` in Recent Transactions, Total spent, the
  Transactions count and the Spending-by-Category breakdown.
* Server-side validation is authoritative. Each of: a blank / zero / negative /
  non-numeric amount, a category outside ``CATEGORIES``, an unparseable or
  blank date, and a description longer than 200 characters -> HTTP 400, the
  form re-rendered with a visible error message, and nothing inserted. The
  values the user did enter are echoed back into the re-rendered form (an
  unparseable date falls back to today).
* The expense owner is always the session user - a ``user_id`` smuggled into
  the ``POST`` body is ignored. All queries are parameterised.
* ``/profile`` carries an "Add expense" CTA linking to
  ``url_for('add_expense')``.
* ``templates/add_expense.html`` and ``static/css/add-expense.css`` use only
  ``var(--...)`` tokens - no ``#rrggbb`` / ``#rgb`` literals.

Isolation mirrors ``tests/test_date_filter_profile.py``: each test runs against
a throwaway SQLite file (``database.db.DB_PATH`` is monkeypatched before
``init_db()`` + ``seed_db()``), so the real ``expense_tracker.db`` is never read
or written.
"""

import re
from datetime import datetime
from pathlib import Path

import pytest
from flask import url_for

from app import app as flask_app

# --------------------------------------------------------------------------- #
# Seed / spec facts - the single source of truth for every expected value.
#
# seed_db() inserts 8 expenses for demo@spendly.com in the *current* month:
#     12.50 Food, 45.00 Transport, 89.99 Bills, 25.00 Health,
#     15.00 Entertainment, 60.00 Shopping, 8.75 Other, 22.30 Food
# -> sum 278.54 ; count 8 ; Food subtotal 34.80 ; 7 distinct categories.
# --------------------------------------------------------------------------- #
SEED_EMAIL = "demo@spendly.com"
SEED_PASSWORD = "demo123"

SEED_EXPENSE_COUNT = 8
RUPEE = "₹"
SEED_TOTAL_DISPLAY = f"{RUPEE}278.54"

# The seven canonical categories the spec pins down (order matters).
CANONICAL_CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]

# A date far enough ahead that the new row is always the newest one, so it is
# guaranteed to land inside the 5-row Recent Transactions window whatever
# calendar day the suite runs on. The spec explicitly adds no future-date check.
FUTURE_DATE = "2099-12-31"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_HEX_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def today_str():
    """Today's date in the stored 'YYYY-MM-DD' form (evaluated at call time)."""
    return datetime.now().strftime("%Y-%m-%d")


def stat_value(value):
    """The exact markup profile.html emits for a summary stat-card value."""
    return f'<div class="stat-value">{value}</div>'


# --------------------------------------------------------------------------- #
# URL helpers - never hardcode paths; always resolve through url_for().
# --------------------------------------------------------------------------- #
def _url(endpoint, **values):
    # test_request_context() (rather than app_context) so url_for resolves to a
    # relative path without needing SERVER_NAME configured.
    with flask_app.test_request_context():
        return url_for(endpoint, **values)


def add_expense_url():
    return _url("add_expense")


def profile_url():
    return _url("profile")


def login_url():
    return _url("login")


# --------------------------------------------------------------------------- #
# Direct access to the throwaway database - parameterised SQL only.
# "No row inserted" is asserted by counting rows in `expenses` before/after.
# --------------------------------------------------------------------------- #
def _db_rows(sql, params=()):
    from database.db import get_db

    conn = get_db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _expense_count():
    return _db_rows("SELECT COUNT(*) AS n FROM expenses")[0]["n"]


def _latest_expense():
    rows = _db_rows("SELECT * FROM expenses ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else None


def _seed_user_id():
    from database.db import get_user_by_email

    return get_user_by_email(SEED_EMAIL)["id"]


# --------------------------------------------------------------------------- #
# HTML probes - deliberately loose so they assert behaviour, not exact layout.
# --------------------------------------------------------------------------- #
def _named_tag(html, tag, name):
    """The opening ``<tag ... name="name" ...>`` element as a string, or None."""
    m = re.search(rf'<{tag}\b[^>]*\bname="{re.escape(name)}"[^>]*>', html, re.S | re.I)
    return m.group(0) if m else None


def _select_block(html, name):
    """The full ``<select name="name"> ... </select>`` block, or None."""
    m = re.search(
        rf'<select\b[^>]*\bname="{re.escape(name)}".*?</select>', html, re.S | re.I
    )
    return m.group(0) if m else None


def _error_text(html):
    """Text of the form's validation error banner, or None.

    The spec says the add-expense form shows an ``{% if error %}`` banner in the
    same role as the auth pages' error block: an element whose class carries
    'error' and whose text is the message.
    """
    m = re.search(
        r'<[a-zA-Z]+[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</[a-zA-Z]+>', html, re.S
    )
    return m.group(1).strip() if m else None


def _option_selected(html, value):
    """True if ``<option value="value" ... selected>`` is present (any order)."""
    return bool(
        re.search(rf'<option[^>]*value="{re.escape(value)}"[^>]*\bselected\b', html, re.I)
        or re.search(rf'<option[^>]*\bselected\b[^>]*value="{re.escape(value)}"', html, re.I)
    )


# --------------------------------------------------------------------------- #
# Fixtures - throwaway seeded SQLite file (mirrors test_date_filter_profile.py)
# --------------------------------------------------------------------------- #
@pytest.fixture
def app(tmp_path, monkeypatch):
    """The real app, pointed at a fresh seeded throwaway SQLite file."""
    import database.db as db_module

    db_file = tmp_path / "spendly_test.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_file))

    flask_app.secret_key = "test-secret"
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        WTF_CSRF_ENABLED=False,
    )

    with flask_app.app_context():
        db_module.init_db()
        db_module.seed_db()
        yield flask_app


@pytest.fixture
def client(app):
    """An unauthenticated test client."""
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """A test client already logged in as the seed demo user."""
    c = app.test_client()
    resp = c.post(login_url(), data={"email": SEED_EMAIL, "password": SEED_PASSWORD})
    assert resp.status_code == 302, (
        f"seed-user login should redirect on success, got {resp.status_code}"
    )
    return c


def _valid_payload(**overrides):
    """A known-good add-expense form body; validation tests mutate one field.

    An override value of ``None`` removes that key entirely (to model a field
    that the browser never submitted).
    """
    data = {
        "amount": "42.50",
        "category": "Food",
        "date": today_str(),
        "description": "Lunch",
    }
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


# --------------------------------------------------------------------------- #
# 1. Auth guards
# --------------------------------------------------------------------------- #
class TestAddExpenseAuthGuard:
    def test_get_add_expense_while_logged_out_redirects_to_login(self, client):
        resp = client.get(add_expense_url())
        assert resp.status_code == 302, "logged-out GET must redirect, not render"
        assert "/login" in resp.headers["Location"], "GET should bounce to /login"

    def test_get_add_expense_while_logged_out_follow_redirect_lands_on_login(self, client):
        resp = client.get(add_expense_url(), follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == login_url(), "should land on the login page"

    def test_post_add_expense_while_logged_out_redirects_to_login_and_inserts_nothing(self, client):
        before = _expense_count()
        resp = client.post(add_expense_url(), data=_valid_payload())
        assert resp.status_code == 302, "logged-out POST must redirect, not process"
        assert "/login" in resp.headers["Location"]
        assert _expense_count() == before, "a logged-out POST must not create an expense"


# --------------------------------------------------------------------------- #
# 2. GET form (authenticated)
# --------------------------------------------------------------------------- #
class TestAddExpenseGetForm:
    def test_get_form_authenticated_returns_200(self, auth_client):
        assert auth_client.get(add_expense_url()).status_code == 200

    def test_get_form_renders_amount_category_date_and_description_fields(self, auth_client):
        html = auth_client.get(add_expense_url()).get_data(as_text=True)
        assert _named_tag(html, "input", "amount") is not None, "missing amount field"
        assert _select_block(html, "category") is not None, "missing category <select>"
        assert _named_tag(html, "input", "date") is not None, "missing date field"
        assert _named_tag(html, "input", "description") is not None, "missing description field"

    def test_get_form_posts_back_to_the_add_expense_route(self, auth_client):
        html = auth_client.get(add_expense_url()).get_data(as_text=True)
        assert re.search(r'<form[^>]*method="post"', html, re.I), "form must use method=POST"
        assert f'action="{add_expense_url()}"' in html, "form must submit to add_expense"

    def test_category_select_lists_exactly_the_seven_categories(self, auth_client):
        from database.db import CATEGORIES

        assert list(CATEGORIES) == CANONICAL_CATEGORIES, (
            "spec fixes the seven canonical categories in this order"
        )

        block = _select_block(
            auth_client.get(add_expense_url()).get_data(as_text=True), "category"
        )
        assert block is not None, "category field should be a <select>"

        for cat in CANONICAL_CATEGORIES:
            assert re.search(
                rf'<option[^>]*>\s*{re.escape(cat)}\s*</option>', block
            ), f"category option missing: {cat}"

        order = [
            re.search(rf'>\s*{re.escape(c)}\s*<', block).start()
            for c in CANONICAL_CATEGORIES
        ]
        assert order == sorted(order), "options should follow CATEGORIES order"

        option_labels = [
            re.sub(r"<[^>]+>", "", chunk).strip()
            for chunk in re.findall(r'<option\b[^>]*>.*?</option>', block, re.S)
        ]
        real = [label for label in option_labels if label in CANONICAL_CATEGORIES]
        assert real == CANONICAL_CATEGORIES, f"expected exactly the seven categories, got {real}"

        extras = [
            label for label in option_labels
            if label and label not in CANONICAL_CATEGORIES
        ]
        assert len(extras) <= 1, (
            f"only a single (disabled) placeholder may accompany the seven categories; extras={extras}"
        )

    def test_date_field_is_prefilled_with_todays_date(self, auth_client):
        today = today_str()
        date_tag = _named_tag(
            auth_client.get(add_expense_url()).get_data(as_text=True), "input", "date"
        )
        assert date_tag is not None, "expected a date input"
        assert f'value="{today}"' in date_tag, f"date field should default to today ({today})"

    def test_fresh_get_form_has_empty_amount_unselected_category_and_empty_description(self, auth_client):
        html = auth_client.get(add_expense_url()).get_data(as_text=True)

        amount_tag = _named_tag(html, "input", "amount")
        assert 'value=""' in amount_tag or "value=" not in amount_tag, "amount should start empty"

        for cat in CANONICAL_CATEGORIES:
            assert not _option_selected(html, cat), f"{cat} should not be pre-selected"

        desc_tag = _named_tag(html, "input", "description")
        assert 'value=""' in desc_tag or "value=" not in desc_tag, "description should start empty"

    def test_fresh_get_form_shows_no_error_banner(self, auth_client):
        html = auth_client.get(add_expense_url()).get_data(as_text=True)
        assert _error_text(html) is None, "a clean GET must not render an error banner"


# --------------------------------------------------------------------------- #
# 3. Happy path POST (authenticated)
# --------------------------------------------------------------------------- #
class TestAddExpenseHappyPath:
    def test_valid_submit_redirects_to_profile(self, auth_client):
        resp = auth_client.post(add_expense_url(), data=_valid_payload())
        assert resp.status_code == 302, "a valid submit should redirect"
        assert "/profile" in resp.headers["Location"], "redirect target should be /profile"

    def test_valid_submit_follow_redirect_lands_on_profile(self, auth_client):
        resp = auth_client.post(
            add_expense_url(), data=_valid_payload(), follow_redirects=True
        )
        assert resp.status_code == 200
        assert resp.request.path == profile_url(), "should land on /profile"

    def test_valid_submit_inserts_exactly_one_row_owned_by_the_logged_in_user(self, auth_client):
        assert _expense_count() == SEED_EXPENSE_COUNT, "seed baseline sanity"
        uid = _seed_user_id()

        resp = auth_client.post(
            add_expense_url(),
            data=_valid_payload(amount="42.50", category="Food", description="Lunch"),
        )
        assert resp.status_code == 302
        assert _expense_count() == SEED_EXPENSE_COUNT + 1, "exactly one new row inserted"
        assert _latest_expense()["user_id"] == uid, (
            "the new expense must belong to the logged-in session user"
        )

    def test_stored_amount_is_a_number_not_a_currency_string(self, auth_client):
        auth_client.post(add_expense_url(), data=_valid_payload(amount="42.50"))
        row = _latest_expense()
        assert isinstance(row["amount"], (int, float)), (
            f"amount should be stored as a REAL number, got {type(row['amount']).__name__}"
        )
        assert row["amount"] == pytest.approx(42.5), "42.50 -> 42.5 in the DB"
        assert RUPEE not in str(row["amount"]), "no currency symbol belongs in the database"

    def test_stored_category_date_and_description_match_the_submission(self, auth_client):
        auth_client.post(
            add_expense_url(),
            data=_valid_payload(
                amount="17.00",
                category="Transport",
                date=today_str(),
                description="Metro card",
            ),
        )
        row = _latest_expense()
        assert row["category"] == "Transport"
        assert row["date"] == today_str()
        assert row["description"] == "Metro card"

    def test_new_expense_amount_is_added_to_total_spent_and_transaction_count_on_profile(self, auth_client):
        auth_client.post(
            add_expense_url(),
            data=_valid_payload(
                amount="137.00", category="Food", description="Quarterly team lunch"
            ),
        )
        html = auth_client.get(profile_url()).get_data(as_text=True)
        # seed total 278.54 + 137.00 = 415.54 ; count 8 + 1 = 9
        assert stat_value(f"{RUPEE}415.54") in html, "Total spent should include the new expense"
        assert stat_value(SEED_EXPENSE_COUNT + 1) in html, "Transactions count should tick up"

    def test_new_expense_is_included_in_the_spending_by_category_breakdown_on_profile(self, auth_client):
        auth_client.post(
            add_expense_url(),
            data=_valid_payload(
                amount="137.00", category="Food", description="Quarterly team lunch"
            ),
        )
        html = auth_client.get(profile_url()).get_data(as_text=True)
        # seed Food subtotal 34.80 + 137.00 = 171.80
        assert f'<span class="category-amount">{RUPEE}171.80</span>' in html, (
            "the Food breakdown row should fold in the new expense"
        )

    def test_new_expense_appears_as_a_row_in_recent_transactions_on_profile(self, auth_client):
        marker = "Dinner at the harbour"
        resp = auth_client.post(
            add_expense_url(),
            data=_valid_payload(
                amount="58.00", category="Food", date=FUTURE_DATE, description=marker
            ),
        )
        assert resp.status_code == 302
        html = auth_client.get(profile_url()).get_data(as_text=True)
        assert marker in html, "the newly added expense should show in Recent Transactions"
        assert html.count('class="txn-amount"') == 5, "Recent Transactions stays capped at 5 rows"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_description_is_stored_as_null(self, auth_client, blank):
        before = _expense_count()
        resp = auth_client.post(
            add_expense_url(), data=_valid_payload(category="Other", description=blank)
        )
        assert resp.status_code == 302, "a blank description is optional, not an error"
        assert _expense_count() == before + 1, "the row is still inserted"
        assert not _latest_expense()["description"], "blank description should persist as NULL/falsy"


# --------------------------------------------------------------------------- #
# 4. Validation errors - 400, form re-rendered with an error, nothing inserted
# --------------------------------------------------------------------------- #
class TestAddExpenseValidation:
    @pytest.mark.parametrize(
        "bad_amount",
        ["", "   ", "0", "0.00", "-5", "-0.01", "abc", "$5"],
        ids=["blank", "whitespace", "zero", "zero-decimal",
             "negative", "tiny-negative", "letters", "currency-prefixed"],
    )
    def test_invalid_amount_is_rejected_with_400_and_no_insert(self, auth_client, bad_amount):
        before = _expense_count()
        resp = auth_client.post(add_expense_url(), data=_valid_payload(amount=bad_amount))
        assert resp.status_code == 400, f"amount={bad_amount!r} must return HTTP 400"
        assert _expense_count() == before, f"amount={bad_amount!r} must insert nothing"
        assert _error_text(resp.get_data(as_text=True)), (
            f"amount={bad_amount!r} must re-render the form with a visible error"
        )

    def test_missing_amount_field_is_rejected_with_400_and_no_insert(self, auth_client):
        before = _expense_count()
        resp = auth_client.post(add_expense_url(), data=_valid_payload(amount=None))
        assert resp.status_code == 400, "an absent amount field must return HTTP 400"
        assert _expense_count() == before
        assert _error_text(resp.get_data(as_text=True))

    @pytest.mark.parametrize(
        "bad_category",
        ["NotACategory", "", "food", "FOOD", "Groceries", "Food ", " Food", "Other;--"],
    )
    def test_category_outside_the_allowed_set_is_rejected_with_400_and_no_insert(
        self, auth_client, bad_category
    ):
        before = _expense_count()
        resp = auth_client.post(add_expense_url(), data=_valid_payload(category=bad_category))
        assert resp.status_code == 400, f"category={bad_category!r} must be rejected"
        assert _expense_count() == before, f"category={bad_category!r} must insert nothing"
        assert _error_text(resp.get_data(as_text=True))

    @pytest.mark.parametrize(
        "bad_date",
        ["banana", "", "   ", "not-a-date", "2026-13-01", "2026-02-30",
         "08-04-2026", "2026/04/08", "20260408", "April 8 2026"],
    )
    def test_unparseable_or_blank_date_is_rejected_with_400_and_no_insert(self, auth_client, bad_date):
        before = _expense_count()
        resp = auth_client.post(add_expense_url(), data=_valid_payload(date=bad_date))
        assert resp.status_code == 400, f"date={bad_date!r} must be rejected"
        assert _expense_count() == before, f"date={bad_date!r} must insert nothing"
        assert _error_text(resp.get_data(as_text=True))

    def test_description_longer_than_200_chars_is_rejected_with_400_and_no_insert(self, auth_client):
        before = _expense_count()
        resp = auth_client.post(add_expense_url(), data=_valid_payload(description="x" * 201))
        assert resp.status_code == 400, "a >200-character description must be rejected"
        assert _expense_count() == before, "nothing should be inserted"
        assert _error_text(resp.get_data(as_text=True))

    def test_description_of_exactly_200_chars_is_accepted(self, auth_client):
        before = _expense_count()
        desc = "x" * 200
        resp = auth_client.post(add_expense_url(), data=_valid_payload(description=desc))
        assert resp.status_code == 302, "200 characters is within the limit, not over it"
        assert _expense_count() == before + 1
        assert _latest_expense()["description"] == desc


# --------------------------------------------------------------------------- #
# 5. Submitted values are echoed back after a validation error
# --------------------------------------------------------------------------- #
class TestAddExpenseErrorEchoesInput:
    def test_validation_error_echoes_back_submitted_category_date_and_description(self, auth_client):
        resp = auth_client.post(
            add_expense_url(),
            data={
                "amount": "abc",                  # the only invalid field
                "category": "Transport",
                "date": "2025-11-20",
                "description": "Monthly metro pass",
            },
        )
        assert resp.status_code == 400
        html = resp.get_data(as_text=True)

        assert _option_selected(html, "Transport"), "submitted category should stay selected"

        date_tag = _named_tag(html, "input", "date")
        assert date_tag is not None and 'value="2025-11-20"' in date_tag, "date should be echoed back"

        desc_tag = _named_tag(html, "input", "description")
        assert desc_tag is not None and 'value="Monthly metro pass"' in desc_tag, (
            "description should be echoed back"
        )

    def test_validation_error_with_unparseable_date_falls_back_to_today_in_the_form(self, auth_client):
        today = today_str()
        resp = auth_client.post(
            add_expense_url(),
            data={
                "amount": "-1",           # invalid -> re-render
                "category": "Food",
                "date": "banana",         # unparseable -> should fall back to today
                "description": "keep me",
            },
        )
        assert resp.status_code == 400
        html = resp.get_data(as_text=True)

        date_tag = _named_tag(html, "input", "date")
        assert date_tag is not None and f'value="{today}"' in date_tag, (
            "an unparseable date should fall back to today in the re-rendered form"
        )
        desc_tag = _named_tag(html, "input", "description")
        assert 'value="keep me"' in desc_tag, "the other entered values are still populated"


# --------------------------------------------------------------------------- #
# 6. Security - the owner is the session user, queries are parameterised
# --------------------------------------------------------------------------- #
class TestAddExpenseSecurity:
    def test_user_id_in_the_form_body_is_ignored(self, auth_client):
        seed_uid = _seed_user_id()
        bogus_uid = seed_uid + 999

        resp = auth_client.post(
            add_expense_url(),
            data=_valid_payload(description="Smuggle attempt", user_id=str(bogus_uid)),
        )
        assert resp.status_code == 302, "a valid submit still succeeds"

        row = _latest_expense()
        assert row["description"] == "Smuggle attempt", "sanity: this is the row we just added"
        assert row["user_id"] == seed_uid, "owner must come from the session, not the form body"
        assert row["user_id"] != bogus_uid

    def test_description_containing_sql_is_stored_as_literal_text(self, auth_client):
        payload_text = "'); DROP TABLE expenses;--"
        before = _expense_count()

        resp = auth_client.post(
            add_expense_url(),
            data=_valid_payload(category="Other", description=payload_text),
        )
        assert resp.status_code == 302
        assert _expense_count() == before + 1, (
            "the expenses table survived -> the value was passed as a SQL parameter"
        )
        assert _latest_expense()["description"] == payload_text, "payload stored verbatim as data"


# --------------------------------------------------------------------------- #
# 7. Profile CTA
# --------------------------------------------------------------------------- #
class TestProfileAddExpenseCta:
    def test_profile_page_has_an_add_expense_link_to_the_form(self, auth_client):
        html = auth_client.get(profile_url()).get_data(as_text=True)
        assert f'href="{add_expense_url()}"' in html, "profile needs an Add expense CTA to the form"
        assert "Add expense" in html, "the CTA should be labelled for the user"

    def test_add_expense_cta_target_is_reachable_when_authenticated(self, auth_client):
        assert auth_client.get(add_expense_url()).status_code == 200, (
            "following the profile CTA should land on the add-expense form"
        )


# --------------------------------------------------------------------------- #
# 8. No hardcoded hex colours
# --------------------------------------------------------------------------- #
class TestAddExpenseNoHardcodedHexColours:
    def test_add_expense_template_uses_only_css_variable_tokens_no_hex(self):
        text = (_PROJECT_ROOT / "templates" / "add_expense.html").read_text(encoding="utf-8")
        matches = _HEX_LITERAL.findall(text)
        assert matches == [], f"add_expense.html must use var(--...) tokens, found hex: {matches}"

    def test_add_expense_css_uses_only_css_variable_tokens_no_hex(self):
        text = (_PROJECT_ROOT / "static" / "css" / "add-expense.css").read_text(encoding="utf-8")
        matches = _HEX_LITERAL.findall(text)
        assert matches == [], f"add-expense.css must use var(--...) tokens, found hex: {matches}"


# --------------------------------------------------------------------------- #
# database/db.py - the new create_expense() helper
# --------------------------------------------------------------------------- #
class TestCreateExpenseDbHelper:
    def test_create_expense_inserts_a_row_and_returns_its_new_id(self, app):
        from database.db import create_expense

        uid = _seed_user_id()
        before = _expense_count()

        new_id = create_expense(uid, 33.25, "Health", "2026-05-01", "Dentist")

        assert _expense_count() == before + 1, "exactly one row inserted"
        row = _latest_expense()
        assert row["id"] == new_id, "create_expense should return the new row id"
        assert row["user_id"] == uid
        assert row["amount"] == pytest.approx(33.25)
        assert row["category"] == "Health"
        assert row["date"] == "2026-05-01"
        assert row["description"] == "Dentist"

    def test_create_expense_defaults_missing_description_to_null(self, app):
        from database.db import create_expense

        create_expense(_seed_user_id(), 5.0, "Other", "2026-05-02")
        assert _latest_expense()["description"] is None, "description defaults to None -> NULL"
