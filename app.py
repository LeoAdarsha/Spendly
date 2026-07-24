import os
from datetime import datetime

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    create_user,
    get_category_totals,
    get_db,
    get_expenses_by_user,
    get_user_by_email,
    get_user_by_id,
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
        return redirect(url_for("landing"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user_by_email(email)

        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template(
                "login.html", error="Invalid email or password."
            ), 401

        session["user_id"] = user["id"]
        return redirect(url_for("landing"))

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
    user_id = session.get("user_id")
    if user_id is None:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    member_since = datetime.strptime(
        user["created_at"], "%Y-%m-%d %H:%M:%S"
    ).strftime("%B %Y")
    initials = "".join(part[0].upper() for part in user["name"].split()[:2])

    expenses = get_expenses_by_user(user_id)
    category_totals = get_category_totals(user_id)

    total_spent = sum(e["amount"] for e in expenses)
    top_category = category_totals[0]["category"] if category_totals else None
    max_category_total = category_totals[0]["total"] if category_totals else 0

    recent_expenses = [
        {
            "date": datetime.strptime(e["date"], "%Y-%m-%d").strftime("%b %d, %Y"),
            "description": e["description"],
            "category": e["category"],
            "tone": CATEGORY_TONE.get(e["category"], "neutral"),
            "amount": format_currency(e["amount"]),
        }
        for e in expenses[:5]
    ]

    categories = [
        {
            "category": row["category"],
            "amount": format_currency(row["total"]),
            "percent": round(row["total"] / max_category_total * 100)
            if max_category_total
            else 0,
        }
        for row in category_totals
    ]

    return render_template(
        "profile.html",
        name=user["name"],
        email=user["email"],
        member_since=member_since,
        initials=initials,
        total_spent=format_currency(total_spent),
        transaction_count=len(expenses),
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
