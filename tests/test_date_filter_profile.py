"""Step 6 - Date Filter for the Profile Page.

Behaviour under test (from the Step 6 brief / definition of done):

* ``GET /profile`` gains two optional, inclusive query params - ``start`` and
  ``end`` (ISO ``YYYY-MM-DD``).  They independently bound the recent-transaction
  list, the summary stats and the category breakdown.
* No query string  -> the full, unfiltered dashboard, exactly as before.
* Only ``start``    -> expenses on/after that date.
* Only ``end``      -> expenses on/before that date.
* A range with no expenses -> Rs 0.00 / 0 transactions / range-aware empty-state
  text in both cards.  ``start`` later than ``end`` -> the same empty view with a
  200 (no server error).
* An unparseable value (``?start=banana``) is silently ignored: 200, full
  unfiltered dashboard, no "Clear" link.  A non-zero-padded value like
  ``2026-7-1`` is accepted and echoed back normalised as ``2026-07-01``.
* The two ``<input type="date">`` fields echo the submitted (validated) values;
  the "Clear" link shows only while a filter is active and points at bare
  ``/profile``.
* Logged-out access to ``/profile?...`` -> 302 to ``/login``.
* ``get_expenses_by_user`` / ``get_category_totals`` in ``database/db.py`` grow
  optional date bounds: called with no date args they behave exactly as before;
  with bounds they filter inclusively; bounds are passed as SQL parameters.
* No ``#rrggbb`` literals introduced in ``templates/profile.html`` or
  ``static/css/profile.css`` - CSS variable tokens only.

Isolation: each test runs against a throwaway SQLite file (``database.db.DB_PATH``
is monkeypatched before ``init_db`` + ``seed_db``), so the project's real
``expense_tracker.db`` is never read or written.
"""

import re
from datetime import datetime
from pathlib import Path

import pytest
from flask import url_for

from app import app as flask_app

# --------------------------------------------------------------------------- #
# Seed facts - the single source of truth for every expected number.
#
# seed_db() inserts 8 expenses for demo@spendly.com on days 2, 4, 5, 9, 12, 15,
# 18 and 21 of the *current* month:
#     12.50 Food       (day 2,  "Groceries at local market")
#     45.00 Transport  (day 4,  "Monthly bus pass")
#     89.99 Bills      (day 5,  "Electricity bill")
#     25.00 Health     (day 9,  "Pharmacy - cold medicine")
#     15.00 Entertainment (day 12, "Movie tickets")
#     60.00 Shopping   (day 15, "New running shoes")
#      8.75 Other      (day 18, "Miscellaneous")
#     22.30 Food       (day 21, "Dinner with friends")
# Sum = 278.54 ; count = 8 ; top category = Bills (89.99) ; 7 distinct categories.
# --------------------------------------------------------------------------- #
SEED_EMAIL = "demo@spendly.com"
SEED_PASSWORD = "demo123"
SEED_NAME = "Demo User"

RUPEE = "₹"
SEED_TOTAL_DISPLAY = f"{RUPEE}278.54"
SEED_COUNT = 8
SEED_TOP_CATEGORY = "Bills"
SEED_CATEGORY_COUNT = 7

# datetime.now() here mirrors seed_db()'s own datetime.now(); both run within the
# same test session, so the year/month agree.
_SEED_NOW = datetime.now()
SEED_MONTH_PREFIX = _SEED_NOW.strftime("%Y-%m")
SEED_YEAR = _SEED_NOW.year
SEED_MONTH = _SEED_NOW.month

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def seed_date(day):
    """Return the stored ``YYYY-MM-DD`` string for a given seed-month day."""
    return _SEED_NOW.replace(day=day).strftime("%Y-%m-%d")


def stat_value(value):
    """The exact markup profile.html emits for a summary stat card value."""
    return f'<div class="stat-value">{value}</div>'


# --------------------------------------------------------------------------- #
# URL helpers - never hardcode paths; always resolve through url_for().
# --------------------------------------------------------------------------- #
def _url(endpoint, **values):
    # test_request_context() (rather than app_context) so url_for resolves to a
    # relative path without needing SERVER_NAME configured.
    with flask_app.test_request_context():
        return url_for(endpoint, **values)


def profile_url(**values):
    return _url("profile", **values)


def login_url():
    return _url("login")


# --------------------------------------------------------------------------- #
# Fixtures
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


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
class TestProfileDateFilterHappyPath:
    def test_profile_no_query_string_renders_full_dashboard(self, auth_client):
        resp = auth_client.get(profile_url())
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # every section still renders
        assert SEED_NAME in html
        assert SEED_EMAIL in html
        assert "Recent Transactions" in html
        assert "Spending by Category" in html

        # full, unfiltered figures
        assert stat_value(SEED_TOTAL_DISPLAY) in html
        assert stat_value(SEED_COUNT) in html
        assert stat_value(SEED_TOP_CATEGORY) in html
        assert html.count('class="category-name"') == SEED_CATEGORY_COUNT
        assert html.count('class="txn-amount"') == 5, "recent list is capped at 5 rows"

        # rupee symbol and no active-filter chrome
        assert RUPEE in html
        assert ">Clear</a>" not in html, "no filter is active -> no Clear link"

    def test_profile_empty_start_and_end_params_match_unfiltered_totals(self, auth_client):
        resp = auth_client.get(profile_url(start="", end=""))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert stat_value(SEED_TOTAL_DISPLAY) in html
        assert stat_value(SEED_COUNT) in html
        assert stat_value(SEED_TOP_CATEGORY) in html
        assert html.count('class="category-name"') == SEED_CATEGORY_COUNT
        assert ">Clear</a>" not in html, "empty params are not an active filter"

    def test_profile_full_seed_month_range_matches_unfiltered_totals(self, auth_client):
        resp = auth_client.get(
            profile_url(start=f"{SEED_MONTH_PREFIX}-01", end=f"{SEED_MONTH_PREFIX}-28")
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # a range that spans the whole seed month == the unfiltered view
        assert stat_value(SEED_TOTAL_DISPLAY) in html
        assert stat_value(SEED_COUNT) in html
        assert stat_value(SEED_TOP_CATEGORY) in html
        assert html.count('class="category-name"') == SEED_CATEGORY_COUNT

        # but the filter is now active -> Clear link back to bare /profile
        assert f'href="{profile_url()}" class="btn-ghost">Clear</a>' in html

    def test_profile_narrow_subrange_reduces_totals_and_breakdown(self, auth_client):
        # days 1..10 -> only the day 2, 4, 5, 9 expenses:
        #   12.50 + 45.00 + 89.99 + 25.00 = 172.49 over 4 transactions
        resp = auth_client.get(
            profile_url(start=f"{SEED_MONTH_PREFIX}-01", end=f"{SEED_MONTH_PREFIX}-10")
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert stat_value(f"{RUPEE}172.49") in html
        assert stat_value(4) in html
        assert stat_value("Bills") in html

        # breakdown shrinks 7 -> 4 categories; out-of-range categories vanish
        assert html.count('class="category-name"') == 4
        assert html.count('class="txn-amount"') == 4
        for absent in ("Shopping", "Entertainment", "Other"):
            assert absent not in html, f"{absent} is outside the sub-range and must not render"


# --------------------------------------------------------------------------- #
# Independent bounds
# --------------------------------------------------------------------------- #
class TestProfileIndependentBounds:
    def test_profile_start_only_includes_expenses_on_or_after(self, auth_client):
        # start = day 15 -> days 15, 18, 21 -> 60.00 + 8.75 + 22.30 = 91.05
        resp = auth_client.get(profile_url(start=seed_date(15)))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert stat_value(f"{RUPEE}91.05") in html
        assert stat_value(3) in html
        assert stat_value("Shopping") in html
        assert html.count('class="category-name"') == 3

        # inclusive lower bound: the day-15 expense is kept
        assert "New running shoes" in html
        # anything earlier is dropped
        assert "Electricity bill" not in html   # day 5
        assert "Monthly bus pass" not in html   # day 4

    def test_profile_end_only_includes_expenses_on_or_before(self, auth_client):
        # end = day 5 -> days 2, 4, 5 -> 12.50 + 45.00 + 89.99 = 147.49
        resp = auth_client.get(profile_url(end=seed_date(5)))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert stat_value(f"{RUPEE}147.49") in html
        assert stat_value(3) in html
        assert stat_value("Bills") in html
        assert html.count('class="category-name"') == 3

        # inclusive upper bound: the day-5 expense is kept
        assert "Electricity bill" in html
        # anything later is dropped
        assert "Movie tickets" not in html        # day 12
        assert "Dinner with friends" not in html  # day 21

    def test_profile_neither_bound_shows_all_time_data(self, auth_client):
        resp = auth_client.get(profile_url())
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert stat_value(SEED_TOTAL_DISPLAY) in html
        assert stat_value(SEED_COUNT) in html
        assert html.count('class="category-name"') == SEED_CATEGORY_COUNT
        assert ">Clear</a>" not in html


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #
class TestProfileDateFilterEdgeCases:
    def test_profile_range_with_no_expenses_shows_zero_state(self, auth_client):
        # same calendar month one year before the seed -> no expenses at all
        empty_year = SEED_YEAR - 1
        resp = auth_client.get(
            profile_url(
                start=f"{empty_year}-{SEED_MONTH:02d}-01",
                end=f"{empty_year}-{SEED_MONTH:02d}-28",
            )
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert stat_value(f"{RUPEE}0.00") in html
        assert stat_value(0) in html
        assert stat_value("—") in html, "top category falls back to an em dash"

        # range-aware empty state in BOTH cards
        assert "No expenses in the selected date range." in html
        assert "No spending data for the selected date range." in html

    def test_profile_start_after_end_returns_empty_view_without_error(self, auth_client):
        resp = auth_client.get(profile_url(start=seed_date(21), end=seed_date(2)))
        assert resp.status_code == 200, "an inverted range must not raise a server error"
        html = resp.get_data(as_text=True)

        assert stat_value(f"{RUPEE}0.00") in html
        assert stat_value(0) in html
        assert "No expenses in the selected date range." in html
        assert "No spending data for the selected date range." in html


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
class TestProfileDateFilterValidation:
    def test_profile_unparseable_start_is_ignored_and_renders_full_dashboard(self, auth_client):
        resp = auth_client.get(profile_url(start="banana"))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert stat_value(SEED_TOTAL_DISPLAY) in html
        assert stat_value(SEED_COUNT) in html
        assert html.count('class="category-name"') == SEED_CATEGORY_COUNT
        assert ">Clear</a>" not in html, "an ignored filter must not show a Clear link"
        assert 'name="start" value=""' in html, "an ignored value is not echoed into the field"

    @pytest.mark.parametrize(
        "bad_value",
        [
            "banana",
            "not-a-date",
            "2026-13-01",   # month out of range
            "2026-02-30",   # day out of range
            "03-09-2026",   # wrong field order
            "2026/09/01",   # wrong separators
            "20260901",     # no separators
        ],
    )
    def test_profile_malformed_dates_fall_back_to_unfiltered(self, auth_client, bad_value):
        resp = auth_client.get(profile_url(start=bad_value, end=bad_value))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert stat_value(SEED_COUNT) in html, "still showing every expense"
        assert stat_value(SEED_TOTAL_DISPLAY) in html
        assert ">Clear</a>" not in html

    @pytest.mark.parametrize(
        "raw, normalised",
        [
            ("2026-7-1", "2026-07-01"),
            ("2026-12-5", "2026-12-05"),
            ("2026-3-09", "2026-03-09"),
        ],
    )
    def test_profile_non_zero_padded_date_is_normalised_and_echoed_back(
        self, auth_client, raw, normalised
    ):
        resp = auth_client.get(profile_url(start=raw))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert f'name="start" value="{normalised}"' in html, (
            "a non-zero-padded date is accepted and echoed back normalised"
        )
        # a valid (if reformatted) bound counts as an active filter
        assert f'href="{profile_url()}" class="btn-ghost">Clear</a>' in html


# --------------------------------------------------------------------------- #
# Filter bar / form persistence UI
# --------------------------------------------------------------------------- #
class TestProfileFilterBarUI:
    def test_profile_date_inputs_echo_submitted_validated_values(self, auth_client):
        start, end = seed_date(5), seed_date(15)
        resp = auth_client.get(profile_url(start=start, end=end))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert f'name="start" value="{start}"' in html
        assert f'name="end" value="{end}"' in html

    def test_profile_clear_link_present_and_targets_bare_profile_when_filter_active(
        self, auth_client
    ):
        resp = auth_client.get(profile_url(start=seed_date(5)))
        html = resp.get_data(as_text=True)

        assert profile_url() == "/profile"
        assert f'href="{profile_url()}" class="btn-ghost">Clear</a>' in html

    def test_profile_clear_link_absent_when_no_filter_active(self, auth_client):
        html = auth_client.get(profile_url()).get_data(as_text=True)
        assert ">Clear</a>" not in html

    def test_profile_clear_link_absent_when_only_bound_is_invalid(self, auth_client):
        html = auth_client.get(profile_url(start="banana", end="")).get_data(as_text=True)
        assert ">Clear</a>" not in html


# --------------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------------- #
class TestProfileDateFilterAuthGuard:
    def test_profile_with_query_string_redirects_to_login_when_logged_out(self, client):
        resp = client.get(profile_url(start=seed_date(1), end=seed_date(28)))
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_profile_with_query_string_follow_redirect_lands_on_login(self, client):
        resp = client.get(profile_url(start=seed_date(1)), follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == "/login"


# --------------------------------------------------------------------------- #
# DB layer - database/db.py helpers
# --------------------------------------------------------------------------- #
class TestDateFilterDbLayer:
    @staticmethod
    def _seed_user_id():
        from database.db import get_user_by_email

        return get_user_by_email(SEED_EMAIL)["id"]

    def test_get_expenses_by_user_without_dates_returns_all_rows_newest_first(self, app):
        from database.db import get_expenses_by_user

        uid = self._seed_user_id()
        rows = get_expenses_by_user(uid)
        assert len(rows) == SEED_COUNT

        # backward compatible: explicit None bounds == no bounds
        rows_none = get_expenses_by_user(uid, None, None)
        assert [r["id"] for r in rows_none] == [r["id"] for r in rows]

        dates = [r["date"] for r in rows]
        assert dates == sorted(dates, reverse=True), "expected date DESC ordering"
        assert dates[0] == seed_date(21)
        assert dates[-1] == seed_date(2)

    def test_get_expenses_by_user_with_bounds_filters_inclusively(self, app):
        from database.db import get_expenses_by_user

        uid = self._seed_user_id()

        both = get_expenses_by_user(uid, seed_date(5), seed_date(15))
        assert {r["date"] for r in both} == {
            seed_date(5), seed_date(9), seed_date(12), seed_date(15)
        }, "both bounds are inclusive"

        start_only = get_expenses_by_user(uid, seed_date(18), None)
        assert {r["date"] for r in start_only} == {seed_date(18), seed_date(21)}

        end_only = get_expenses_by_user(uid, None, seed_date(4))
        assert {r["date"] for r in end_only} == {seed_date(2), seed_date(4)}

    def test_get_category_totals_without_dates_is_backward_compatible(self, app):
        from database.db import get_category_totals

        uid = self._seed_user_id()
        totals = get_category_totals(uid)

        assert len(totals) == SEED_CATEGORY_COUNT
        assert totals[0]["category"] == "Bills"
        assert round(totals[0]["total"], 2) == 89.99
        assert round(sum(t["total"] for t in totals), 2) == 278.54

        again = get_category_totals(uid, None, None)
        assert [(t["category"], round(t["total"], 2)) for t in again] == [
            (t["category"], round(t["total"], 2)) for t in totals
        ]

    def test_get_category_totals_with_bounds_filters_inclusively(self, app):
        from database.db import get_category_totals

        uid = self._seed_user_id()
        # days 1..10 -> Bills 89.99, Transport 45.00, Health 25.00, Food 12.50
        totals = get_category_totals(uid, seed_date(1), seed_date(10))

        assert [t["category"] for t in totals] == ["Bills", "Transport", "Health", "Food"]
        assert {t["category"]: round(t["total"], 2) for t in totals} == {
            "Bills": 89.99,
            "Transport": 45.00,
            "Health": 25.00,
            "Food": 12.50,
        }

    def test_date_bounds_are_passed_as_sql_parameters_not_string_formatted(self, app):
        from database.db import get_category_totals, get_expenses_by_user

        uid = self._seed_user_id()
        injection_low = "0000'; DROP TABLE expenses;--"
        injection_high = "9999'; DROP TABLE expenses;--"

        # As an upper bound: nothing sorts at/under it, and the payload is inert data.
        assert list(get_expenses_by_user(uid, None, injection_low)) == []
        # As a lower bound on the aggregate query.
        assert list(get_category_totals(uid, injection_high, None)) == []

        # The DROP TABLE never executed -> the schema and data are intact.
        assert len(get_expenses_by_user(uid)) == SEED_COUNT, (
            "expenses table survived the injection -> the bound was parameterised"
        )
        assert len(get_category_totals(uid)) == SEED_CATEGORY_COUNT


# --------------------------------------------------------------------------- #
# No hardcoded hex colours
# --------------------------------------------------------------------------- #
class TestNoHardcodedHexColours:
    _HEX_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b")

    def test_profile_template_uses_only_css_variable_tokens_no_hex(self):
        text = (_PROJECT_ROOT / "templates" / "profile.html").read_text(encoding="utf-8")
        matches = self._HEX_LITERAL.findall(text)
        assert matches == [], f"profile.html must use var(--...) tokens, found hex: {matches}"

    def test_profile_css_uses_only_css_variable_tokens_no_hex(self):
        text = (_PROJECT_ROOT / "static" / "css" / "profile.css").read_text(encoding="utf-8")
        matches = self._HEX_LITERAL.findall(text)
        assert matches == [], f"profile.css must use var(--...) tokens, found hex: {matches}"
