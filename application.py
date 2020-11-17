import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # get the amount of cash with the user
    user = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cashRemaining = user[0]["cash"]

    # get info about user's transactions
    transaction = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > -1", user_id=session["user_id"])

    # dictionary to sto re current/latest info about shares
    quote = {}

    for stock in transaction:
        quote[stock["symbol"]] = lookup(stock["symbol"])

    for stock in transaction:
        money = quote[stock["symbol"]]["price"] * stock["total_shares"]
        quote[stock["symbol"]].update({"worthShares": money})

    currentMoney = 0
    for stock in transaction:
        currentMoney += quote[stock["symbol"]]["worthShares"]
    currentMoney += cashRemaining


    return render_template("index.html", quote=quote, transaction=transaction, currentMoney=currentMoney, cashRemaining=cashRemaining)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # invloked by post method
    if request.method == "POST":

        # get the quote
        quote = lookup(request.form.get("symbol"))

        # if the lookup function return none; means lookup function couldn't find share
        if quote == None:
            return apology("symbol not found", 400)

        # checking if the number of shared entered is valid
        shares = int(request.form.get("shares"))
        if shares <= 0:
            return apology("invalid number of shared entered", 400)

        # Check if user has necessary funds
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])

        cashRemaining = rows[0]["cash"]
        sharePrice = quote["price"]
        total = sharePrice * shares

        # if yes, proceed with the transaction
        if total <= cashRemaining:
            db.execute("UPDATE users SET cash = cash - :cost WHERE id = :user_id", cost=total, user_id=session["user_id"])
            db.execute("INSERT INTO transactions (user_id, symbol, shares, share_price) VALUES(:user_id, :symbol, :shares, :share_price)",
                       user_id=session["user_id"],
                       symbol=request.form.get("symbol"),
                       shares=shares,
                       share_price=sharePrice)
            db.execute("INSERT INTO buy (user_id, symbol, shares, share_price) VALUES(:user_id, :symbol, :shares, :price)",
                       user_id=session["user_id"],
                       symbol=request.form.get("symbol"),
                       shares=shares,
                       price=sharePrice)

            flash("Bought the shares successfully!")
            return redirect("/")
        # otherwise
        else:
            return apology("not enough money to buy shares")

    # invoked by get method
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    buys = db.execute("SELECT symbol, shares, share_price, timestamp from buy where user_id = :user_id order by timestamp desc", user_id=session["user_id"])
    sells = db.execute("SELECT symbol, shares, share_price, timestamp from sell where user_id = :user_id order by timestamp desc", user_id=session["user_id"])

    return render_template("history.html", buys=buys, sells=sells)

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
    """Get stock quote."""

    # if post method is invoked
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))

        # if lookup function returns none
        if quote == None:
            return apology("invalid symbol", 400)
        #otherwise go to quoted
        return render_template("quoted.html", quote=quote)

    # if get method is invoked
    else:
        return render_template("quote.html")


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register the new user"""

    # checking request method post i.e if user submitted the form
    if request.method == "POST":
        # double checking if user didn't leave any field empty; otherwise giving an error
        username = request.form.get("username")
        if not username:
            return apology("Enter a username to register!", 400)
        password = request.form.get("password")
        if not password:
            return apology("Enter a password to register!", 400)
        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("Please confirm your password!", 400)

        # double checking for unique username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(rows) != 0:
            return apology("username already exists", 400)

        # double checking for password matching with confrimed password
        if password != confirmation:
            return apology("both the entered passwords don't match", 400)

        # hashing the password
        hash = generate_password_hash(password)
        # inserting the information of the user into the users table thus registering him
        user_id = db.execute("insert into users (username, hash) values(:username, :hash)", username=username, hash=hash)

        # redirecting him to index page
        flash("Registered!")
        session["user_id"] = user_id
        return redirect("/")

    # checking request method get
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # if post method is invoked
    if request.method == "POST":

        # check if that stock actually exists
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("symbol doesn't exist", 400)

        stock = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol", user_id=session["user_id"], symbol=request.form.get("symbol"))

        # check if that user has shares of that stock
        if len(stock) != 1 or stock[0]["symbol"] != request.form.get("symbol"):
            return apology("You don't have shares of this stock!", 400)

        # check if shares entered are valid
        shares = int(request.form.get("shares"))
        if shares <= 0:
            return apology("invalid amount of shares entered", 400)

        # Check if user has enough shares
        if len(stock) != 1 or stock[0]["total_shares"] < int(request.form.get("shares")):
            return apology("you cannot sell more than you own", 400)

        user = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])

        # cash with the user
        cashRemaining = user[0]["cash"]

        # current price of sold shares
        sharePrice = quote["price"]
        totalPrice = sharePrice * shares


        # updating the database
        db.execute("UPDATE users SET cash = cash + :price WHERE id = :user_id", price=totalPrice, user_id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, share_price) VALUES(:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"],
                   symbol=request.form.get("symbol"),
                   shares=-shares,
                   price=sharePrice)
        db.execute("INSERT INTO sell (user_id, symbol, shares, share_price) VALUES(:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"],
                   symbol=request.form.get("symbol"),
                   shares=shares,
                   price=sharePrice)


        # back to index.html
        flash("Sold!")
        return redirect("/")


    # if get method is invoked
    else:
        return render_template("sell.html")


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """Allow user to change her password"""

    if request.method == "POST":
        # Ensure current password is not empty
        if not request.form.get("current_password"):
            return apology("must provide current password", 400)

        # Query database for user_id
        rows = db.execute("SELECT hash FROM users WHERE id = :user_id", user_id=session["user_id"])

        # Ensure current password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("current_password")):
            return apology("invalid password", 400)

        # Ensure new password is not empty
        if not request.form.get("new_password"):
            return apology("must provide new password", 400)

        # Ensure new password confirmation is not empty
        elif not request.form.get("new_password_confirmation"):
            return apology("must provide new password confirmation", 400)

        # Ensure new password and confirmation match
        elif request.form.get("new_password") != request.form.get("new_password_confirmation"):
            return apology("new password and confirmation must match", 400)

        # Update database
        hash = generate_password_hash(request.form.get("new_password"))
        rows = db.execute("UPDATE users SET hash = :hash WHERE id = :user_id", user_id=session["user_id"], hash=hash)

        # Show flash
        flash("Changed!")
        return redirect("/")

    else:
        return render_template("change_password.html")



def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
