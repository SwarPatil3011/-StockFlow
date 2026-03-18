import mysql.connector

from flask import Flask, render_template, request, redirect

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Swar2006@#",
    database="stockflow_db"
)

cursor = db.cursor(dictionary=True)
app = Flask(__name__)

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():

    username = request.form["username"]
    password = request.form["password"]

    cursor.execute(
        "SELECT * FROM users WHERE username=%s AND password=%s",
        (username, password)
    )

    user = cursor.fetchone()

    if user:
        return render_template("index.html")
    else:
        return "Wrong username or password"

@app.route("/products")
def products():
    search = request.args.get("search")

    if search:
        cursor.execute(
            "SELECT * FROM products WHERE name LIKE %s",
            ("%" + search + "%",)
        )
    else:
        cursor.execute("SELECT * FROM products")

    product_list = cursor.fetchall()
    return render_template("products.html", products=product_list)

@app.route("/delete_product/<int:id>", methods=["POST"])
def delete_product(id):
    cursor.execute("DELETE FROM products WHERE id = %s", (id,))
    db.commit()
    return redirect("/products")

@app.route("/add_product", methods=["POST"])
def add_product():
    name = request.form["name"]
    price = request.form["price"]
    quantity = request.form["quantity"]

    cursor.execute(
        "INSERT INTO products (name, price, quantity) VALUES (%s, %s, %s)",
        (name, price, quantity)
    )
    db.commit()

    return redirect("/products")

@app.route("/edit_product/<int:id>")
def edit_product(id):
    cursor.execute("SELECT * FROM products WHERE id = %s", (id,))
    product = cursor.fetchone()
    return render_template("edit_product.html", product=product)

@app.route("/update_product/<int:id>", methods=["POST"])
def update_product(id):
    name = request.form["name"]
    price = request.form["price"]
    quantity = request.form["quantity"]

    cursor.execute(
        "UPDATE products SET name=%s, price=%s, quantity=%s WHERE id=%s",
        (name, price, quantity, id)
    )
    db.commit()

    return redirect("/products")

if __name__ == "__main__":
    app.run(debug=True)