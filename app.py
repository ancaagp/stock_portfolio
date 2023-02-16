import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

def calculate_shares(user_id):
    cash = db.execute("SELECT cash FROM users WHERE id=?", user_id)
    cash = cash[0]["cash"]

    rows = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id=? AND transaction_type='bought' GROUP BY symbol", user_id)
    shares_bought = dict()
    for row in rows:
        shares_bought[row["symbol"]] = row["total_shares"]

    rows = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id=? AND transaction_type='sold' GROUP BY symbol", user_id)
    shares_sold = dict()
    for row in rows:
        shares_sold[row["symbol"]] = row["total_shares"]

    for symbol in shares_sold.keys():
        shares_bought[symbol] -= shares_sold[symbol]

    transactions = []
    total = 0
    for symbol in shares_bought.keys():
        stock = lookup(symbol)
        transaction = dict()
        transaction["symbol"] = symbol
        transaction["name"] = stock["name"]
        transaction["price"] = usd(stock["price"])
        transaction["shares"] = shares_bought[symbol]
        transaction["total"] = usd(stock["price"] * transaction["shares"])
        total += stock["price"] * transaction["shares"]
        transactions.append(transaction)

    total += cash

    return transactions, cash, total


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    user_id = session["user_id"]
    transactions, cash, total = calculate_shares(user_id)

    return render_template("index.html", transactions = transactions, total = usd(total), cash = usd(cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    user_id = session["user_id"]

    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)

        if (stock == None) or (symbol == ""):
            return apology("invalid symbol", 403)

        stock_price = stock["price"]
        stock_symbol = stock["symbol"]
        stock_name = stock["name"]
        shares = float(request.form.get("shares"))
        user_id = session["user_id"]

        rows = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        cash = rows[0]['cash']
        price_bought = shares * stock_price

        if cash < price_bought:
            return apology("not enough funds", 403)

        # save in the table a new row with user id, symbol, shares, prices, date
        db.execute("INSERT INTO transactions (name, symbol, shares, price, transacted, user_id, transaction_type) VALUES (?,?,?,?,?,?,?)", stock_name, stock_symbol, shares, stock_price, datetime.datetime.now(), user_id, "bought")

        # substract price from cash and update in users table
        new_cash = cash - price_bought

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, user_id)

        transactions, cash, total = calculate_shares(user_id)

        return render_template("index.html", transactions = transactions, total = usd(total), cash = usd(cash), message = "bought")
    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    user_id = session["user_id"]
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", user_id)

    for transaction in transactions:
        transaction["price"] = usd(transaction["price"])
        if transaction["transaction_type"] == "sold":
            transaction["shares"] = transaction["shares"] * -1

    return render_template("history.html", transactions = transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")



@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        symbol = request.form.get("quote")
        quote = lookup(symbol)

        if quote == None:
            return apology("invalid symbol", 403)

        return render_template("quoted.html", name=quote["name"], symbol=quote["symbol"], price=usd(quote["price"]))
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

        # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username = request.form.get("username")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        usernamecheck = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Ensure username is not taken
        if len(usernamecheck) > 0:
            return apology("username is already taken", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure passwords match
        elif request.form.get("password")!= request.form.get("password2"):
            return apology("passwords don't match", 403)

        # Add user to database (hash password)
        hash = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES (?,?)", username, hash)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Log User in and return to "/"
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    user_id = session["user_id"]
    transactions = db.execute("SELECT symbol, SUM(shares) AS total_shares FROM transactions WHERE user_id = ? GROUP BY symbol", user_id)

    if request.method == "POST":
        symbol = request.form.get("symbol")

        if symbol == None:
            return apology("missing symbol", 400)

        stock = lookup(symbol)
        user_stock = next(item for item in transactions if item["symbol"] == symbol)
        shares_sold = request.form.get("shares")

        if shares_sold == "":
            return apology("missing shares", 400)

        if user_stock["total_shares"] < int(shares_sold):
            return apology("not enough shares", 400)

        # save transaction into db
        db.execute("INSERT INTO transactions (name, symbol, shares, price, transacted, user_id, transaction_type) VALUES (?,?,?,?,?,?,?)", stock["name"], symbol, shares_sold, stock["price"], datetime.datetime.now(), user_id, "sold")

        # update user cash into db
        cash = db.execute("SELECT cash from users where id=?", user_id)
        cash_bought = int(shares_sold) * stock["price"]
        new_cash = cash[0]["cash"] + cash_bought

        db.execute("UPDATE users SET cash=? WHERE id=?", new_cash, user_id)

        transactions, cash, total = calculate_shares(user_id)
        return render_template("index.html", transactions = transactions, total = usd(total), cash = usd(cash), message = "sold")

    return render_template("sell.html", transactions = transactions)
