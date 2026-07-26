import os

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    create_user,
    get_db,
    get_user_by_email,
    init_db,
    seed_db,
)

CATEGORY_TONE = {
    "Food": "accent",
    "Transport": "neutral",
    "Bills": "accent",
    "Health": "accent",
    "Entertainment": "amber",
    "Shopping": "neutral",
    "Other": "neutral",
}


# Step 4 shows the finished profile layout with static data so the design can be
# validated before any queries exist. Step 5 replaces everything below with real
# lookups against the users/expenses tables.
PROFILE_USER = {
    "initials": "NS",
    "name": "Nitish Singh",
    "email": "nitish@spendly.com",
    "member_since": "January 2025",
}

PROFILE_TRANSACTIONS = [
    {"date": "Apr 08, 2026", "description": "Lunch with colleagues", "category": "Food", "amount": 180.00},
    {"date": "Apr 08, 2026", "description": "Miscellaneous", "category": "Other", "amount": 200.00},
    {"date": "Apr 07, 2026", "description": "New earphones", "category": "Shopping", "amount": 800.00},
    {"date": "Apr 06, 2026", "description": "Movie tickets", "category": "Entertainment", "amount": 500.00},
    {"date": "Apr 05, 2026", "description": "Pharmacy — vitamins", "category": "Health", "amount": 350.00},
    {"date": "Apr 03, 2026", "description": "Electricity bill", "category": "Bills", "amount": 1200.00},
    {"date": "Apr 02, 2026", "description": "Metro card recharge", "category": "Transport", "amount": 120.00},
    {"date": "Apr 01, 2026", "description": "Groceries at the local market", "category": "Food", "amount": 450.00},
]

# Highest first, so the first entry drives the width of every progress bar.
PROFILE_CATEGORY_TOTALS = [
    ("Bills", 1200.00),
    ("Shopping", 800.00),
    ("Food", 630.00),
    ("Entertainment", 500.00),
    ("Health", 350.00),
    ("Other", 200.00),
    ("Transport", 120.00),
]

RECENT_LIMIT = 5


def format_currency(amount):
    return "₹{:,.2f}".format(amount)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.context_processor
def inject_current_user():
    # Step 4 is UI-only: the navbar name comes from the same hardcoded
    # profile constant. Step 5 replaces this with get_user_by_id().
    if session.get("user_id") is None:
        return {"current_user_name": None}
    return {"current_user_name": PROFILE_USER["name"]}


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id") is not None:
        return redirect(url_for("landing"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password.strip():
            return render_template(
                "register.html", error="All fields are required."
            ), 400

        if get_user_by_email(email) is not None:
            return render_template(
                "register.html", error="Email already registered."
            ), 400

        password_hash = generate_password_hash(password)
        user_id = create_user(name, email, password_hash)
        session["user_id"] = user_id
        return redirect(url_for("landing"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id") is not None:
        return redirect(url_for("profile"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user_by_email(email)

        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template(
                "login.html", error="Invalid email or password."
            ), 401

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if session.get("user_id") is None:
        return redirect(url_for("login"))

    total_spent = sum(t["amount"] for t in PROFILE_TRANSACTIONS)
    top_category = PROFILE_CATEGORY_TOTALS[0][0] if PROFILE_CATEGORY_TOTALS else None
    max_category_total = (
        PROFILE_CATEGORY_TOTALS[0][1] if PROFILE_CATEGORY_TOTALS else 0
    )

    recent_expenses = [
        {
            "date": t["date"],
            "description": t["description"],
            "category": t["category"],
            "tone": CATEGORY_TONE.get(t["category"], "neutral"),
            "amount": format_currency(t["amount"]),
        }
        for t in PROFILE_TRANSACTIONS[:RECENT_LIMIT]
    ]

    categories = []
    for category, total in PROFILE_CATEGORY_TOTALS:
        percent = round(total / max_category_total * 100) if max_category_total else 0
        categories.append(
            {
                "category": category,
                "amount": format_currency(total),
                "percent": percent,
                # Bar widths come from CSS classes in 5% steps — the spec
                # forbids inline styles, so the width can't be interpolated.
                "percent_step": round(percent / 5) * 5,
            }
        )

    return render_template(
        "profile.html",
        name=PROFILE_USER["name"],
        email=PROFILE_USER["email"],
        member_since=PROFILE_USER["member_since"],
        initials=PROFILE_USER["initials"],
        total_spent=format_currency(total_spent),
        transaction_count=len(PROFILE_TRANSACTIONS),
        top_category=top_category,
        recent_expenses=recent_expenses,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
