"""Step 8 - Edit Expense.

Behaviour under test, taken straight from ``.claude/Specs/08-edit-expense.md``
(its Routes, Rules for implementation, and Definition of done sections). These
tests describe what the feature *should* do; they never reverse-engineer the
current implementation of ``edit_expense`` or the new ``database/db.py`` helpers.

* ``/expenses/<int:id>/edit`` serves a ``GET`` form and a validated ``POST``
  handler. Both require a logged-in session: a logged-out request is redirected
  to ``/login`` (302) and a logged-out ``POST`` must not modify the row.
* ``GET`` (authenticated, own expense) returns 200 and renders Amount, Category,
  Date and Description fields *pre-filled with that expense's current stored
  values*. The Category ``<select>`` marks the stored category as ``selected``;
  the form ``method`` is ``post`` and its ``action`` targets ``edit_expense``
  for that id; the submit button reads "Save changes".
* Ownership is enforced server-side in SQL. As the seed user, ``GET`` or ``POST``
  to an expense id owned by a different user -> 404 and that row is untouched.
  ``GET /expenses/999999/edit`` (no such row) -> 404.
* A valid ``POST`` updates exactly that one row (amount, category, date,
  description) and redirects to ``/profile`` (302). ``id``, ``user_id`` and
  ``created_at`` are left untouched; no row is inserted or deleted; the amount
  is stored as a plain number (no currency symbol). A blank description is
  stored as NULL. The updated values then show on ``/profile`` (Recent
  Transactions / Total spent / Transactions count / Spending by Category).
* Server-side validation is authoritative and identical to Step 7. Each of: a
  blank / whitespace / zero / negative / non-numeric / missing amount, a
  category outside ``CATEGORIES``, an unparseable or blank date, and a
  description longer than 200 characters -> HTTP 400, the form re-rendered with
  a visible error banner, and the target row byte-for-byte unchanged. A
  description of exactly 200 characters is accepted.
* After a validation error the submitted amount / category / date / description
  are echoed back into the form. An *unparseable* submitted date falls back to
  the expense's STORED date -- NOT today (this differs from add-expense).
* Security: a ``user_id`` smuggled into the ``POST`` body is ignored (the row
  keeps its original owner); a description containing SQL is stored as literal
  text and the ``expenses`` table survives (parameterised queries).
* ``/profile`` Recent Transactions gains a per-row **Edit** link built with
  ``url_for('edit_expense', id=e.id)``; the list stays capped at 5 rows.
* ``templates/edit_expense.html`` and ``static/css/edit-expense.css`` use only
  ``var(--...)`` tokens -- no ``#rrggbb`` / ``#rgb`` literals.
* ``database/db.py`` helpers: ``get_expense_by_id(expense_id, user_id)`` returns
  the row for the owner and ``None`` for a wrong owner / missing id;
  ``update_expense(expense_id, user_id, amount, category, date, description)``
  updates only the matching-owner row, leaves ``created_at`` untouched, and
  returns 0 when nothing matches.

Isolation mirrors ``tests/test_add_expense.py`` /
``tests/test_date_filter_profile.py``: each test runs against a throwaway
SQLite file (``database.db.DB_PATH`` is monkeypatched before ``init_db()`` +
``seed_db()``), so the real ``expense_tracker.db`` is never read or written.
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
#     12.50 Food        (day 2,  "Groceries at local market")
#     45.00 Transport   (day 4,  "Monthly bus pass")
#     89.99 Bills       (day 5,  "Electricity bill")
#     25.00 Health      (day 9,  "Pharmacy - cold medicine")
#     15.00 Entertainment (day 12, "Movie tickets")
#     60.00 Shopping    (day 15, "New running shoes")
#      8.75 Other       (day 18, "Miscellaneous")
#     22.30 Food        (day 21, "Dinner with friends")
# -> sum 278.54 ; count 8 ; Food subtotal 34.80 ; 7 distinct categories.
# --------------------------------------------------------------------------- #
SEED_EMAIL = "demo@spendly.com"
SEED_PASSWORD = "demo123"

SEED_EXPENSE_COUNT = 8
SEED_CATEGORY_COUNT = 7
RUPEE = "₹"
SEED_TOTAL_DISPLAY = f"{RUPEE}278.54"

# The seven canonical categories the spec pins down (order matters).
CANONICAL_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

# Seed rows used as edit targets, addressed by their (unique) descriptions.
#   * GET_TARGET_DESC -> "Electricity bill": Bills / day 5 / 89.99. Chosen for
#     the GET pre-fill test because it does NOT collide with the description
#     input's placeholder text ("e.g. Groceries at local market").
#   * EDIT_TARGET_DESC -> "Groceries at local market": Food / day 2 / 12.50.
#     Used for POST tests; editing its category (Food -> Bills) proves the write.
GET_TARGET_DESC = "Electricity bill"
EDIT_TARGET_DESC = "Groceries at local market"

# A date far enough ahead that an edited row is always the newest one, so it is
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


def edit_expense_url(expense_id):
    return _url("edit_expense", id=expense_id)


def profile_url():
    return _url("profile")


def login_url():
    return _url("login")


# --------------------------------------------------------------------------- #
# Direct access to the throwaway database - parameterised SQL only.
# "No row inserted/deleted" is asserted by counting rows in `expenses`;
# "row unchanged" by snapshotting every column before/after.
# --------------------------------------------------------------------------- #
def _db_rows(sql, params=()):
    from database.db import get_db

    conn = get_db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _db_exec(sql, params=()):
    """Run a single parameterised write against the throwaway DB (test setup)."""
    from database.db import get_db

    conn = get_db()
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _expense_count():
    return _db_rows("SELECT COUNT(*) AS n FROM expenses")[0]["n"]


def _expense_by_id(expense_id):
    rows = _db_rows("SELECT * FROM expenses WHERE id = ?", (expense_id,))
    return rows[0] if rows else None


def _row_snapshot(expense_id):
    """Every column of one expense row as a plain tuple, or None if absent."""
    rows = _db_rows(
        "SELECT id, user_id, amount, category, date, description, created_at "
        "FROM expenses WHERE id = ?",
        (expense_id,),
    )
    return tuple(rows[0]) if rows else None


def _seed_expense_by_description(description):
    rows = _db_rows("SELECT * FROM expenses WHERE description = ?", (description,))
    assert rows, f"expected a seeded expense with description {description!r}"
    return rows[0]


def _seed_user_id():
    from database.db import get_user_by_email

    return get_user_by_email(SEED_EMAIL)["id"]


def _make_second_user_expense(
    amount=10.0,
    category="Food",
    date="2020-01-15",
    description="Second user's expense",
):
    """Create a SECOND user owning one expense; return (user_id, expense_id).

    Used for ownership tests - the seed user must never be able to read or write
    this row through /expenses/<id>/edit.
    """
    from database.db import create_expense, create_user

    other_uid = create_user("Other User", "other@spendly.com", "not-a-real-hash")
    other_eid = create_expense(other_uid, amount, category, date, description)
    return other_uid, other_eid


# --------------------------------------------------------------------------- #
# HTML probes - deliberately loose so they assert behaviour, not exact layout.
# --------------------------------------------------------------------------- #
def _named_tag(html, tag, name):
    """The opening ``<tag ... name="name" ...>`` element as a string, or None."""
    m = re.search(rf'<{tag}\b[^>]*\bname="{re.escape(name)}"[^>]*>', html, re.S | re.I)
    return m.group(0) if m else None


def _input_value(tag_str):
    """The ``value="..."`` attribute text of a rendered input tag, or None."""
    if tag_str is None:
        return None
    m = re.search(r'value="([^"]*)"', tag_str)
    return m.group(1) if m else None


def _select_block(html, name):
    """The full ``<select name="name"> ... </select>`` block, or None."""
    m = re.search(
        rf'<select\b[^>]*\bname="{re.escape(name)}".*?</select>', html, re.S | re.I
    )
    return m.group(0) if m else None


def _error_text(html):
    """Text of the form's validation error banner, or None.

    The spec says edit-expense mirrors add-expense: an ``{% if error %}`` banner
    in the same role as the auth pages' error block -- an element whose class
    carries 'error' and whose text is the message.
    """
    m = re.search(
        r'<[a-zA-Z]+[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</[a-zA-Z]+>', html, re.S
    )
    return m.group(1).strip() if m else None


def _option_selected(html, value):
    """True if ``<option value="value" ... selected>`` is present (any order)."""
    return bool(
        re.search(
            rf'<option[^>]*value="{re.escape(value)}"[^>]*\bselected\b', html, re.I
        )
        or re.search(
            rf'<option[^>]*\bselected\b[^>]*value="{re.escape(value)}"', html, re.I
        )
    )


# --------------------------------------------------------------------------- #
# Fixtures - throwaway seeded SQLite file (mirrors test_add_expense.py)
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
    assert (
        resp.status_code == 302
    ), f"seed-user login should redirect on success, got {resp.status_code}"
    return c


def _valid_payload(**overrides):
    """A known-good edit form body; validation tests mutate one field.

    An override value of ``None`` removes that key entirely (to model a field
    that the browser never submitted).
    """
    data = {
        "amount": "55.00",
        "category": "Health",
        "date": "2026-06-15",
        "description": "Edited note",
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
class TestEditExpenseAuthGuard:
    def test_get_edit_while_logged_out_redirects_to_login(self, client):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        resp = client.get(edit_expense_url(eid))
        assert resp.status_code == 302, "logged-out GET must redirect, not render"
        assert "/login" in resp.headers["Location"], "GET should bounce to /login"

    def test_get_edit_while_logged_out_follow_redirect_lands_on_login(self, client):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        resp = client.get(edit_expense_url(eid), follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == login_url(), "should land on the login page"

    def test_post_edit_while_logged_out_redirects_to_login_and_row_unchanged(
        self, client
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        before = _row_snapshot(eid)
        resp = client.post(edit_expense_url(eid), data=_valid_payload())
        assert resp.status_code == 302, "logged-out POST must redirect, not process"
        assert "/login" in resp.headers["Location"]
        assert _row_snapshot(eid) == before, "a logged-out POST must not modify the row"


# --------------------------------------------------------------------------- #
# 2. GET form (authenticated, own expense)
# --------------------------------------------------------------------------- #
class TestEditExpenseGetForm:
    def test_get_form_for_own_expense_returns_200(self, auth_client):
        eid = _seed_expense_by_description(GET_TARGET_DESC)["id"]
        assert auth_client.get(edit_expense_url(eid)).status_code == 200

    def test_get_form_renders_amount_category_date_and_description_fields(
        self, auth_client
    ):
        eid = _seed_expense_by_description(GET_TARGET_DESC)["id"]
        html = auth_client.get(edit_expense_url(eid)).get_data(as_text=True)
        assert _named_tag(html, "input", "amount") is not None, "missing amount field"
        assert _select_block(html, "category") is not None, "missing category <select>"
        assert _named_tag(html, "input", "date") is not None, "missing date field"
        assert (
            _named_tag(html, "input", "description") is not None
        ), "missing description field"

    def test_get_form_prefills_every_field_with_the_stored_values(self, auth_client):
        expense = _seed_expense_by_description(GET_TARGET_DESC)
        html = auth_client.get(edit_expense_url(expense["id"])).get_data(as_text=True)

        amount_tag = _named_tag(html, "input", "amount")
        assert amount_tag is not None, "expected an amount input"
        assert _input_value(amount_tag) is not None, "amount field should be pre-filled"
        assert float(_input_value(amount_tag)) == pytest.approx(
            expense["amount"]
        ), "amount field must show the expense's current stored amount"

        date_tag = _named_tag(html, "input", "date")
        assert (
            date_tag is not None and f'value="{expense["date"]}"' in date_tag
        ), "date field must show the expense's current stored date"

        desc_tag = _named_tag(html, "input", "description")
        assert (
            desc_tag is not None and f'value="{expense["description"]}"' in desc_tag
        ), "description field must show the expense's current stored description"

    def test_get_form_marks_the_stored_category_as_selected(self, auth_client):
        expense = _seed_expense_by_description("Movie tickets")  # Entertainment
        assert expense["category"] == "Entertainment", "seed fact sanity"
        html = auth_client.get(edit_expense_url(expense["id"])).get_data(as_text=True)

        assert (
            _select_block(html, "category") is not None
        ), "category should be a <select>"
        assert _option_selected(
            html, "Entertainment"
        ), "the stored category must be the pre-selected <option>"
        for other in CANONICAL_CATEGORIES:
            if other != "Entertainment":
                assert not _option_selected(
                    html, other
                ), f"{other} must not be pre-selected"

    def test_get_form_posts_back_to_edit_expense_for_that_id(self, auth_client):
        eid = _seed_expense_by_description(GET_TARGET_DESC)["id"]
        url = edit_expense_url(eid)
        html = auth_client.get(url).get_data(as_text=True)
        assert re.search(
            r'<form[^>]*method="post"', html, re.I
        ), "form must use method=POST"
        assert f'action="{url}"' in html, "form must submit to edit_expense for this id"

    def test_get_form_submit_button_reads_save_changes(self, auth_client):
        eid = _seed_expense_by_description(GET_TARGET_DESC)["id"]
        html = auth_client.get(edit_expense_url(eid)).get_data(as_text=True)
        assert "Save changes" in html, "the submit button label must be 'Save changes'"

    def test_get_form_shows_no_error_banner(self, auth_client):
        eid = _seed_expense_by_description(GET_TARGET_DESC)["id"]
        html = auth_client.get(edit_expense_url(eid)).get_data(as_text=True)
        assert _error_text(html) is None, "a clean GET must not render an error banner"


# --------------------------------------------------------------------------- #
# 3. Ownership - another user's id, or a missing id, is a 404
# --------------------------------------------------------------------------- #
class TestEditExpenseOwnership:
    def test_get_another_users_expense_returns_404(self, auth_client):
        _, other_eid = _make_second_user_expense()
        resp = auth_client.get(edit_expense_url(other_eid))
        assert resp.status_code == 404, "another user's expense must be 404, not 200"

    def test_post_another_users_expense_returns_404_and_row_unchanged(
        self, auth_client
    ):
        _, other_eid = _make_second_user_expense()
        before = _row_snapshot(other_eid)
        resp = auth_client.post(edit_expense_url(other_eid), data=_valid_payload())
        assert resp.status_code == 404, "POST to another user's expense must be 404"
        assert _row_snapshot(other_eid) == before, "that row must be left untouched"

    def test_get_missing_expense_id_returns_404(self, auth_client):
        assert auth_client.get(edit_expense_url(999999)).status_code == 404

    def test_post_missing_expense_id_returns_404_and_writes_nothing(self, auth_client):
        before = _expense_count()
        resp = auth_client.post(edit_expense_url(999999), data=_valid_payload())
        assert resp.status_code == 404
        assert _expense_count() == before, "a 404 POST must not insert a row"


# --------------------------------------------------------------------------- #
# 4. Happy path - valid edit updates one row in place, redirects to /profile
# --------------------------------------------------------------------------- #
class TestEditExpenseHappyPath:
    def test_valid_edit_redirects_to_profile(self, auth_client):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        resp = auth_client.post(edit_expense_url(eid), data=_valid_payload())
        assert resp.status_code == 302, "a valid edit should redirect"
        assert (
            "/profile" in resp.headers["Location"]
        ), "redirect target should be /profile"

    def test_valid_edit_follow_redirect_lands_on_profile(self, auth_client):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        resp = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(), follow_redirects=True
        )
        assert resp.status_code == 200
        assert resp.request.path == profile_url(), "should land on /profile"

    def test_valid_edit_updates_that_one_row_in_place(self, auth_client):
        expense = _seed_expense_by_description(EDIT_TARGET_DESC)
        eid, owner = expense["id"], expense["user_id"]
        assert expense["category"] == "Food", "seed fact sanity"

        resp = auth_client.post(
            edit_expense_url(eid),
            data=_valid_payload(
                amount="99.00",
                category="Bills",
                date="2026-04-08",
                description="Fixed rent",
            ),
        )
        assert resp.status_code == 302

        row = _expense_by_id(eid)
        assert row["id"] == eid, "the same row is updated, not a new one"
        assert row["user_id"] == owner, "user_id is never touched by an edit"
        assert row["amount"] == pytest.approx(99.0)
        assert row["category"] == "Bills"
        assert row["date"] == "2026-04-08"
        assert row["description"] == "Fixed rent"

    def test_valid_edit_leaves_created_at_untouched(self, auth_client):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        # Pin created_at to a distinctive value so any re-touch is visible.
        _db_exec(
            "UPDATE expenses SET created_at = ? WHERE id = ?",
            ("2018-01-02 03:04:05", eid),
        )
        resp = auth_client.post(edit_expense_url(eid), data=_valid_payload())
        assert resp.status_code == 302
        assert (
            _expense_by_id(eid)["created_at"] == "2018-01-02 03:04:05"
        ), "created_at must not be in the UPDATE ... SET list"

    def test_valid_edit_does_not_insert_or_delete_rows(self, auth_client):
        before = _expense_count()
        assert before == SEED_EXPENSE_COUNT, "seed baseline sanity"
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        resp = auth_client.post(edit_expense_url(eid), data=_valid_payload())
        assert resp.status_code == 302
        assert _expense_count() == before, "an edit must not change the total row count"

    def test_valid_edit_stores_amount_as_a_number_not_a_currency_string(
        self, auth_client
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        auth_client.post(edit_expense_url(eid), data=_valid_payload(amount="99.00"))
        row = _expense_by_id(eid)
        assert isinstance(
            row["amount"], (int, float)
        ), f"amount should stay a REAL number, got {type(row['amount']).__name__}"
        assert row["amount"] == pytest.approx(99.0), "99.00 -> 99.0 in the DB"
        assert RUPEE not in str(row["amount"]), "no currency symbol belongs in the DB"

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_description_is_stored_as_null(self, auth_client, blank):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        resp = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(description=blank)
        )
        assert resp.status_code == 302, "a blank description is optional, not an error"
        assert (
            _expense_by_id(eid)["description"] is None
        ), "a blank description must persist as NULL"

    def test_updated_values_show_on_profile(self, auth_client):
        baseline = auth_client.get(profile_url()).get_data(as_text=True)
        assert stat_value(SEED_TOTAL_DISPLAY) in baseline, "seed baseline sanity"

        # "Groceries at local market": Food 12.50 -> Bills 99.00.
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        resp = auth_client.post(
            edit_expense_url(eid),
            data=_valid_payload(
                amount="99.00",
                category="Bills",
                date=FUTURE_DATE,
                description="Fixed rent",
            ),
        )
        assert resp.status_code == 302

        html = auth_client.get(profile_url()).get_data(as_text=True)
        # Total spent: 278.54 - 12.50 + 99.00 = 365.04 ; count stays 8.
        assert stat_value(f"{RUPEE}365.04") in html, "Total spent must reflect the edit"
        assert stat_value(SEED_EXPENSE_COUNT) in html, "Transactions count is unchanged"
        # Bills is now the biggest category: 89.99 + 99.00 = 188.99.
        assert stat_value("Bills") in html, "top category becomes Bills"
        assert (
            f'<span class="category-amount">{RUPEE}188.99</span>' in html
        ), "the Bills breakdown row folds in the edited expense"
        # Food shrinks to the single remaining 22.30 expense.
        assert (
            f'<span class="category-amount">{RUPEE}22.30</span>' in html
        ), "the Food breakdown row loses the edited expense"
        assert (
            html.count('class="category-name"') == SEED_CATEGORY_COUNT
        ), "Food still keeps one expense -> 7 categories remain"
        # The edited row (future-dated) shows its new description in Recent.
        assert "Fixed rent" in html, "the edited row appears in Recent Transactions"


# --------------------------------------------------------------------------- #
# 5. Validation - 400, error banner, target row byte-for-byte unchanged
# --------------------------------------------------------------------------- #
class TestEditExpenseValidation:
    @pytest.mark.parametrize(
        "bad_amount",
        ["", "   ", "0", "0.00", "-5", "abc"],
        ids=["blank", "whitespace", "zero", "zero-decimal", "negative", "letters"],
    )
    def test_invalid_amount_is_rejected_with_400_and_row_unchanged(
        self, auth_client, bad_amount
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        before = _row_snapshot(eid)
        resp = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(amount=bad_amount)
        )
        assert resp.status_code == 400, f"amount={bad_amount!r} must return HTTP 400"
        assert _error_text(
            resp.get_data(as_text=True)
        ), f"amount={bad_amount!r} must re-render the form with a visible error"
        assert (
            _row_snapshot(eid) == before
        ), f"amount={bad_amount!r} must not modify the row"

    def test_missing_amount_field_is_rejected_with_400_and_row_unchanged(
        self, auth_client
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        before = _row_snapshot(eid)
        resp = auth_client.post(edit_expense_url(eid), data=_valid_payload(amount=None))
        assert resp.status_code == 400, "an absent amount field must return HTTP 400"
        assert _error_text(resp.get_data(as_text=True))
        assert _row_snapshot(eid) == before

    @pytest.mark.parametrize("bad_category", ["NotACategory", "", "food", "Food "])
    def test_invalid_category_is_rejected_with_400_and_row_unchanged(
        self, auth_client, bad_category
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        before = _row_snapshot(eid)
        resp = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(category=bad_category)
        )
        assert resp.status_code == 400, f"category={bad_category!r} must be rejected"
        assert _error_text(resp.get_data(as_text=True))
        assert (
            _row_snapshot(eid) == before
        ), f"category={bad_category!r} must not modify the row"

    @pytest.mark.parametrize(
        "bad_date",
        [
            "banana",
            "",
            "   ",
            "2026-13-01",
            "2026/04/08",
            "08-04-2026",
            "20260408",
            "April 8 2026",
        ],
    )
    def test_invalid_date_is_rejected_with_400_and_row_unchanged(
        self, auth_client, bad_date
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        before = _row_snapshot(eid)
        resp = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(date=bad_date)
        )
        assert resp.status_code == 400, f"date={bad_date!r} must be rejected"
        assert _error_text(resp.get_data(as_text=True))
        assert (
            _row_snapshot(eid) == before
        ), f"date={bad_date!r} must not modify the row"

    def test_description_longer_than_200_chars_is_rejected_with_400_and_row_unchanged(
        self, auth_client
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        before = _row_snapshot(eid)
        resp = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(description="x" * 201)
        )
        assert resp.status_code == 400, "a >200-character description must be rejected"
        assert _error_text(resp.get_data(as_text=True))
        assert _row_snapshot(eid) == before, "nothing should be written"

    def test_description_of_exactly_200_chars_is_accepted(self, auth_client):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        before_count = _expense_count()
        desc = "x" * 200
        resp = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(description=desc)
        )
        assert (
            resp.status_code == 302
        ), "200 characters is within the limit, not over it"
        assert _expense_count() == before_count, "an edit never changes the row count"
        assert _expense_by_id(eid)["description"] == desc


# --------------------------------------------------------------------------- #
# 6. Submitted values are echoed back after a validation error
# --------------------------------------------------------------------------- #
class TestEditExpenseErrorEchoesInput:
    def test_validation_error_echoes_back_amount_category_and_description(
        self, auth_client
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        resp = auth_client.post(
            edit_expense_url(eid),
            data={
                "amount": "abc",  # the only invalid field
                "category": "Transport",
                "date": "2025-11-20",
                "description": "Echo me back",
            },
        )
        assert resp.status_code == 400
        html = resp.get_data(as_text=True)

        assert (
            _input_value(_named_tag(html, "input", "amount")) == "abc"
        ), "the submitted amount is echoed back verbatim"
        assert _option_selected(html, "Transport"), "submitted category stays selected"

        date_tag = _named_tag(html, "input", "date")
        assert (
            date_tag is not None and 'value="2025-11-20"' in date_tag
        ), "a valid submitted date is echoed back"

        desc_tag = _named_tag(html, "input", "description")
        assert (
            desc_tag is not None and 'value="Echo me back"' in desc_tag
        ), "the submitted description is echoed back"

    def test_unparseable_date_falls_back_to_the_stored_date_not_today(
        self, auth_client
    ):
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        # First a valid edit pins the stored date to a fixed, non-today value.
        seeded = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(date="2001-02-03")
        )
        assert seeded.status_code == 302
        assert _expense_by_id(eid)["date"] == "2001-02-03", "setup sanity"

        resp = auth_client.post(
            edit_expense_url(eid),
            data={
                "amount": "not-a-number",  # invalid -> re-render
                "category": "Bills",
                "date": "banana",  # unparseable -> fall back to stored
                "description": "keep me",
            },
        )
        assert resp.status_code == 400
        html = resp.get_data(as_text=True)

        date_tag = _named_tag(html, "input", "date")
        assert date_tag is not None, "expected a date input"
        assert (
            'value="2001-02-03"' in date_tag
        ), "an unparseable date must fall back to the expense's STORED date"
        assert (
            f'value="{today_str()}"' not in date_tag
        ), "edit-expense must NOT fall back to today (that is add-expense behaviour)"
        assert 'value="keep me"' in _named_tag(
            html, "input", "description"
        ), "the other entered values are still populated"


# --------------------------------------------------------------------------- #
# 7. Security - the owner never comes from the form; queries are parameterised
# --------------------------------------------------------------------------- #
class TestEditExpenseSecurity:
    def test_user_id_in_the_form_body_is_ignored(self, auth_client):
        seed_uid = _seed_user_id()
        bogus_uid = seed_uid + 999
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]

        resp = auth_client.post(
            edit_expense_url(eid),
            data=_valid_payload(description="Owner check", user_id=str(bogus_uid)),
        )
        assert resp.status_code == 302, "a valid edit still succeeds"

        row = _expense_by_id(eid)
        assert row["description"] == "Owner check", "sanity: this is the row we edited"
        assert row["user_id"] == seed_uid, "owner must stay the original session user"
        assert row["user_id"] != bogus_uid, "the smuggled user_id must be ignored"

    def test_description_containing_sql_is_stored_as_literal_text(self, auth_client):
        payload_text = "'); DROP TABLE expenses;--"
        before = _expense_count()
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]

        resp = auth_client.post(
            edit_expense_url(eid), data=_valid_payload(description=payload_text)
        )
        assert resp.status_code == 302
        assert (
            _expense_count() == before
        ), "the expenses table survived -> the value was passed as a SQL parameter"
        assert (
            _expense_by_id(eid)["description"] == payload_text
        ), "the payload is stored verbatim as data"


# --------------------------------------------------------------------------- #
# 8. Profile Recent Transactions gains a per-row Edit link
# --------------------------------------------------------------------------- #
class TestProfileEditLink:
    @staticmethod
    def _recent_ids(uid):
        return [
            r["id"]
            for r in _db_rows(
                "SELECT id FROM expenses WHERE user_id = ? "
                "ORDER BY date DESC, id DESC LIMIT 5",
                (uid,),
            )
        ]

    def test_every_recent_transaction_row_has_an_edit_link_to_its_expense(
        self, auth_client
    ):
        recent_ids = self._recent_ids(_seed_user_id())
        assert len(recent_ids) == 5, "seed data should fill the 5-row recent window"

        html = auth_client.get(profile_url()).get_data(as_text=True)
        for eid in recent_ids:
            assert (
                f'href="{edit_expense_url(eid)}"' in html
            ), f"Recent Transactions row {eid} needs an Edit link built with url_for"
        assert ">Edit</a>" in html, "the per-row link should be labelled 'Edit'"

    def test_recent_transaction_edit_links_are_reachable_with_200(self, auth_client):
        for eid in self._recent_ids(_seed_user_id()):
            resp = auth_client.get(edit_expense_url(eid))
            assert (
                resp.status_code == 200
            ), f"following the Edit link for expense {eid} should render the form"

    def test_recent_transactions_stay_capped_at_five_edit_links(self, auth_client):
        html = auth_client.get(profile_url()).get_data(as_text=True)
        assert (
            html.count('class="txn-action"') == 5
        ), "Recent Transactions (and its Edit column) stays capped at 5 rows"


# --------------------------------------------------------------------------- #
# 9. No hardcoded hex colours in the new template / stylesheet
# --------------------------------------------------------------------------- #
class TestEditExpenseNoHardcodedHexColours:
    def test_edit_expense_template_uses_only_css_variable_tokens_no_hex(self):
        text = (_PROJECT_ROOT / "templates" / "edit_expense.html").read_text(
            encoding="utf-8"
        )
        matches = _HEX_LITERAL.findall(text)
        assert (
            matches == []
        ), f"edit_expense.html must use var(--...) tokens, found hex: {matches}"

    def test_edit_expense_css_uses_only_css_variable_tokens_no_hex(self):
        text = (_PROJECT_ROOT / "static" / "css" / "edit-expense.css").read_text(
            encoding="utf-8"
        )
        matches = _HEX_LITERAL.findall(text)
        assert (
            matches == []
        ), f"edit-expense.css must use var(--...) tokens, found hex: {matches}"


# --------------------------------------------------------------------------- #
# 10. database/db.py - get_expense_by_id() and update_expense()
# --------------------------------------------------------------------------- #
class TestEditExpenseDbHelpers:
    def test_get_expense_by_id_returns_the_row_for_its_owner(self, app):
        from database.db import get_expense_by_id

        uid = _seed_user_id()
        seeded = _seed_expense_by_description(GET_TARGET_DESC)

        row = get_expense_by_id(seeded["id"], uid)
        assert row is not None, "the owner must be able to load their own expense"
        assert row["id"] == seeded["id"]
        assert row["user_id"] == uid
        assert row["category"] == seeded["category"]

    def test_get_expense_by_id_returns_none_for_a_wrong_owner(self, app):
        from database.db import get_expense_by_id

        other_uid, other_eid = _make_second_user_expense()
        seed_uid = _seed_user_id()
        seeded = _seed_expense_by_description(GET_TARGET_DESC)

        assert (
            get_expense_by_id(other_eid, seed_uid) is None
        ), "the seed user must not load the second user's expense"
        assert (
            get_expense_by_id(seeded["id"], other_uid) is None
        ), "the second user must not load a seed expense"

    def test_get_expense_by_id_returns_none_for_a_missing_id(self, app):
        from database.db import get_expense_by_id

        assert get_expense_by_id(999999, _seed_user_id()) is None

    def test_update_expense_updates_only_the_matching_owner_row(self, app):
        from database.db import get_expense_by_id, update_expense

        uid = _seed_user_id()
        target = _seed_expense_by_description(EDIT_TARGET_DESC)
        untouched_before = _row_snapshot(
            _seed_expense_by_description(GET_TARGET_DESC)["id"]
        )

        changed = update_expense(
            target["id"], uid, 77.0, "Bills", "2022-02-02", "changed"
        )
        assert changed == 1, "exactly one owned row is updated"

        row = get_expense_by_id(target["id"], uid)
        assert row["amount"] == pytest.approx(77.0)
        assert row["category"] == "Bills"
        assert row["date"] == "2022-02-02"
        assert row["description"] == "changed"

        untouched_after = _row_snapshot(
            _seed_expense_by_description(GET_TARGET_DESC)["id"]
        )
        assert untouched_after == untouched_before, "other rows are left alone"

    def test_update_expense_leaves_created_at_untouched(self, app):
        from database.db import update_expense

        uid = _seed_user_id()
        eid = _seed_expense_by_description(EDIT_TARGET_DESC)["id"]
        _db_exec(
            "UPDATE expenses SET created_at = ? WHERE id = ?",
            ("2019-05-05 05:05:05", eid),
        )

        update_expense(eid, uid, 33.0, "Health", "2023-03-03", "x")

        assert (
            _expense_by_id(eid)["created_at"] == "2019-05-05 05:05:05"
        ), "created_at must not appear in the UPDATE ... SET list"

    def test_update_expense_returns_zero_for_a_wrong_owner_and_changes_nothing(
        self, app
    ):
        from database.db import update_expense

        other_uid, _ = _make_second_user_expense()
        target = _seed_expense_by_description(GET_TARGET_DESC)
        before = _row_snapshot(target["id"])

        changed = update_expense(
            target["id"], other_uid, 1.0, "Food", "2000-01-01", "hijack"
        )
        assert changed == 0, "a mismatched owner matches no rows"
        assert _row_snapshot(target["id"]) == before, "the row is untouched"

    def test_update_expense_returns_zero_for_a_missing_id(self, app):
        from database.db import update_expense

        changed = update_expense(
            999999, _seed_user_id(), 1.0, "Food", "2000-01-01", "nope"
        )
        assert changed == 0
