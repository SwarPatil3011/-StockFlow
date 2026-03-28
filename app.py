import mysql.connector
import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, session


db = mysql.connector.connect(
    host="localhost",
    user="root",
    password=os.getenv("DB_PASSWORD"),
    database="stockflow_db"
)

cursor = db.cursor(dictionary=True)
app = Flask(__name__)
app.secret_key = "secret123"

@app.route("/")
def home():
    return redirect('/login')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect('/dashboard')

    if request.method == 'POST':
        username = request.form["username"]
        password = request.form["password"]

        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password)
        )

        user = cursor.fetchone()

        if user:
            session['user'] = username
            return redirect('/dashboard')
        else:
            return "Wrong username or password"

    return render_template("login.html")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')

    return render_template('index.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

@app.route("/products")
def products():
    if 'user' not in session:
        return redirect('/login')
    
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
    if 'user' not in session:
        return redirect('/login')
    
    cursor.execute("DELETE FROM products WHERE id = %s", (id,))
    db.commit()
    return redirect("/products")

@app.route("/add_product", methods=["POST"])
def add_product():
    if 'user' not in session:
        return redirect('/login')
    
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
    if 'user' not in session:
        return redirect('/login')
    
    cursor.execute("SELECT * FROM products WHERE id = %s", (id,))
    product = cursor.fetchone()
    return render_template("edit_product.html", product=product)

@app.route("/update_product/<int:id>", methods=["POST"])
def update_product(id):
    if 'user' not in session:
        return redirect('/login')
    
    name = request.form["name"]
    price = request.form["price"]
    quantity = request.form["quantity"]

    cursor.execute(
        "UPDATE products SET name=%s, price=%s, quantity=%s WHERE id=%s",
        (name, price, quantity, id)
    )
    db.commit()

    return redirect("/products")

# This is for creating a bill
# This is INPUT / ACTION
# like make a bill but we cannot see them
@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if 'user' not in session:
        return redirect('/login')

    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    total = None
    message = None

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = request.form.get('quantity')

        # safety check
        if not product_id or not quantity:
            message = "Please fill all fields"
            return render_template('billing.html', products=products, total=total, message=message)

        quantity = int(quantity)

        cursor.execute("SELECT price, quantity FROM products WHERE id=%s", (product_id,))
        data = cursor.fetchone()

        if not data:
            message = "Product not found"
            return render_template('billing.html', products=products, total=total, message=message)

        price = data['price']
        stock = data['quantity']

        if quantity > stock:
            message = "Not enough stock available!"
            return render_template('billing.html', products=products, total=total, message=message)

        # SUCCESS CASE
        total = price * quantity

        new_stock = stock - quantity
        cursor.execute("UPDATE products SET quantity=%s WHERE id=%s", (new_stock, product_id))

        cursor.execute(
            "INSERT INTO bills (product_id, quantity, total) VALUES (%s, %s, %s)",
            (product_id, quantity, total)
        )

        db.commit()

        bill_id = cursor.lastrowid
        return redirect(f"/invoice/{bill_id}")

    # GET request (default page load)
    return render_template('billing.html', products=products, total=total, message=message)

@app.route('/bills')
def bills():
    if 'user' not in session:
        return redirect('/login')

    query = """
    SELECT 
        bills.id,
        products.name,
        bills.quantity,
        bills.total,
        bills.date
    FROM bills
    JOIN products ON bills.product_id = products.id
    ORDER BY bills.id ASC       #bills will store serially 1,2,3..
    """
    
    print(query)

    cursor.execute(query)
    all_bills = cursor.fetchall()

    return render_template('bills.html', bills=all_bills)

# Use bills.quantity for invoice and bills page (Quantity sold in that bill, You sold 2 Milk → bills.quantity = 2)
# Use products.quantity for stock management (Quantity currently available in stock, * You had 10 Milk * Sold 2 → now products.quantity = 8)

@app.route('/invoice/<int:bill_id>')
def invoice(bill_id):
    if 'user' not in session:
        return redirect('/login')
    
    query = """
    SELECT 
         bills.id,
         products.name,
         bills.quantity,
         bills.total,
         bills.date
    FROM bills
    JOIN products ON bills.product_id = products.id
    WHERE bills.id = %s
    """

    cursor.execute(query, (bill_id,))
    bill = cursor.fetchone()

    return render_template('invoice.html', bill = bill)

@app.route('/redtock', methods=['POST'])
def restock():
    product_id = request.form['product_id']  # product_id → which product to update
    add_qty = int(request.form['quantity'])  # quantity → how much to add

    conn = get_db_connection()  # conn → connection
    cursor = conn,cursor()  # cursor → used to run SQL queries

     # 1. Get current stock
    cursor.execute("SELECT quantity FROM products WHERE id = %s", (product_id,))  # Find current stock of that product
    current_stock = cursor.fetchone()[0]

    # 2. Add quantity
    new_stock = current_stock + add_qty

    # 3. Update DB
    cursor.execute("UPDATE products SET quantity = %s WHERE id = %s", (new_stock, product_id))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect('/products')


if __name__ == "__main__":
    app.run(debug=True)