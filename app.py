import mysql.connector
import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, session


def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.getenv("DB_PASSWORD"),
        database="stockflow_db"
    )


base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")

app = Flask(__name__, template_folder=template_dir)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.secret_key = "secret123"


@app.route("/")
def home():
    return redirect('/login')


@app.route("/login", methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect('/dashboard')

    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor(dictionary=True, buffered=True)

        username = request.form["username"]
        password = request.form["password"]

        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password)
        )

        user = cursor.fetchone()
        cursor.close()
        db.close()

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

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    # 1. Total Sales (sum of all bills)
    cursor.execute("SELECT COALESCE(SUM(total), 0) AS total_sales FROM bills")
    total_sales = cursor.fetchone()['total_sales']

    # 2. Total Purchase Cost
    cursor.execute("SELECT COALESCE(SUM(cost), 0) AS total_cost FROM purchases")
    total_cost = cursor.fetchone()['total_cost']

    # 3. Monthly Profit (revenue - cost)
    monthly_profit = total_sales - total_cost

    # 4. Low Stock Items (quantity < 10)
    cursor.execute("SELECT name, quantity FROM products WHERE quantity < 10 ORDER BY quantity ASC")
    low_stock_items = cursor.fetchall()

    # 5. Top 5 Products by quantity sold
    cursor.execute("""
        SELECT products.name, SUM(bills.quantity) AS total_sold
        FROM bills
        JOIN products ON bills.product_id = products.id
        GROUP BY products.name
        ORDER BY total_sold DESC
        LIMIT 5
    """)
    top_products = cursor.fetchall()

    # 6. Sales Trend — last 7 days
    cursor.execute("""
        SELECT DATE(date) AS day, COALESCE(SUM(total), 0) AS daily_total
        FROM bills
        WHERE date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        GROUP BY DATE(date)
        ORDER BY day ASC
    """)
    trend_data = cursor.fetchall()

    cursor.close()
    db.close()

    # Prepare chart data as lists
    trend_labels = [str(row['day']) for row in trend_data]
    trend_values = [float(row['daily_total']) for row in trend_data]

    return render_template('index.html',
        total_sales=total_sales,
        total_cost=total_cost,
        monthly_profit=monthly_profit,
        low_stock_items=low_stock_items,
        top_products=top_products,
        trend_labels=trend_labels,
        trend_values=trend_values
    )


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')


@app.route("/products")
def products():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Load all categories for tabs + modal
    cursor.execute("SELECT * FROM categories ORDER BY name ASC")
    categories = cursor.fetchall()

    # Category filter
    selected_category = request.args.get("category")
    search = request.args.get("search")

    query = """
        SELECT products.*, categories.name AS category_name
        FROM products
        LEFT JOIN categories ON products.category_id = categories.id
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND products.name LIKE %s"
        params.append("%" + search + "%")

    if selected_category:
        query += " AND products.category_id = %s"
        params.append(selected_category)

    query += " ORDER BY products.name ASC"

    cursor.execute(query, params)
    product_list = cursor.fetchall()
    cursor.close()
    db.close()

    for p in product_list:
        p['low_stock'] = p['quantity'] < 10

    # Convert selected_category to int for template comparison
    selected_category = int(selected_category) if selected_category else None

    return render_template("products.html",
        products=product_list,
        categories=categories,
        selected_category=selected_category
    )


@app.route("/add_product", methods=["POST"])
def add_product():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor()

    name = request.form["name"]
    price = request.form["price"]
    quantity = request.form["quantity"]
    category_id = request.form.get("category_id") or None

    cursor.execute(
        "INSERT INTO products (name, price, quantity, category_id) VALUES (%s, %s, %s, %s)",
        (name, price, quantity, category_id)
    )
    db.commit()
    cursor.close()
    db.close()

    return redirect("/products")


@app.route("/edit_product/<int:id>")
def edit_product(id):
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("SELECT * FROM products WHERE id = %s", (id,))
    product = cursor.fetchone()

    cursor.execute("SELECT * FROM categories ORDER BY name ASC")
    categories = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("edit_product.html", product=product, categories=categories)


@app.route("/update_product/<int:id>", methods=["POST"])
def update_product(id):
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor()

    name = request.form["name"]
    price = request.form["price"]
    quantity = request.form["quantity"]
    category_id = request.form.get("category_id") or None

    cursor.execute(
        "UPDATE products SET name=%s, price=%s, quantity=%s, category_id=%s WHERE id=%s",
        (name, price, quantity, category_id, id)
    )
    db.commit()
    cursor.close()
    db.close()

    return redirect("/products")

@app.route("/categories")
def categories():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT categories.id, categories.name,
               COUNT(products.id) AS product_count
        FROM categories
        LEFT JOIN products ON products.category_id = categories.id
        GROUP BY categories.id, categories.name
        ORDER BY categories.name ASC
    """)
    cats = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template("categories.html", categories=cats)


@app.route("/add_category", methods=["POST"])
def add_category():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor()
    name = request.form["name"].strip()

    if name:
        cursor.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
        db.commit()

    cursor.close()
    db.close()
    return redirect("/categories")


@app.route("/delete_category/<int:id>", methods=["POST"])
def delete_category(id):
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor()
    # Set category_id to NULL for products in this category
    cursor.execute("UPDATE products SET category_id = NULL WHERE category_id = %s", (id,))
    cursor.execute("DELETE FROM categories WHERE id = %s", (id,))
    db.commit()
    cursor.close()
    db.close()
    return redirect("/categories")

# This is for creating a bill
# This is INPUT / ACTION
# like make a bill but we cannot see them
@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    total = None
    message = None

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = request.form.get('quantity')

        if not product_id or not quantity:
            message = "Please fill all fields"
            cursor.close()
            db.close()
            return render_template('billing.html', products=products, total=total, message=message)

        quantity = int(quantity)

        cursor.execute("SELECT price, quantity FROM products WHERE id=%s", (product_id,))
        data = cursor.fetchone()

        if not data:
            message = "Product not found"
            cursor.close()
            db.close()
            return render_template('billing.html', products=products, total=total, message=message)

        price = data['price']
        stock = data['quantity']

        if quantity > stock:
            message = "Not enough stock available!"
            cursor.close()
            db.close()
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
        cursor.close()
        db.close()

        return redirect(f"/invoice/{bill_id}")

    cursor.close()
    db.close()
    return render_template('billing.html', products=products, total=total, message=message)


@app.route('/bills')
def bills():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    query = """
    SELECT
        bills.id,
        products.name,
        bills.quantity,
        bills.total,
        bills.date
    FROM bills
    JOIN products ON bills.product_id = products.id
    ORDER BY bills.id ASC
    """

    cursor.execute(query)
    all_bills = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('bills.html', bills=all_bills)

# Use bills.quantity for invoice and bills page (Quantity sold in that bill, You sold 2 Milk → bills.quantity = 2)
# Use products.quantity for stock management (Quantity currently available in stock, * You had 10 Milk * Sold 2 → now products.quantity = 8)

@app.route('/invoice/<int:bill_id>')
def invoice(bill_id):
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

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
    cursor.close()
    db.close()

    return render_template('invoice.html', bill=bill)


@app.route('/restock', methods=['POST'])
def restock():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    product_id = request.form['product_id']    # product_id → which product to update
    add_qty = int(request.form['quantity'])    # add_qty → how many quantity to add

    # 1. Get current stock
    cursor.execute("SELECT quantity FROM products WHERE id = %s", (product_id,))     # Find current stock of that product
    current_stock = cursor.fetchone()['quantity']   # Get the quantity value from the result

    # 2. Add quantity
    new_stock = current_stock + add_qty

    # 3. Update DB
    cursor.execute("UPDATE products SET quantity = %s WHERE id = %s", (new_stock, product_id))
    db.commit()
    cursor.close()
    db.close()

    return redirect('/products')


@app.route('/purchase', methods=['GET', 'POST'])
def purchase():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Load dropdown data
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    cursor.execute("SELECT * FROM suppliers")
    suppliers = cursor.fetchall()

    if request.method == 'POST':
        product_id = request.form['product_id']
        supplier_id = request.form['supplier_id']
        quantity = int(request.form['quantity'])
        cost = float(request.form['cost'])

        # Save purchase
        cursor.execute(
            "INSERT INTO purchases (supplier_id, product_id, quantity, cost) VALUES (%s, %s, %s, %s)",
            (supplier_id, product_id, quantity, cost)
        )

        # Get current stock
        cursor.execute("SELECT quantity FROM products WHERE id=%s", (product_id,))
        current_stock = cursor.fetchone()['quantity']

        # Update stock
        new_stock = current_stock + quantity

        cursor.execute(
            "UPDATE products SET quantity=%s WHERE id=%s",
            (new_stock, product_id)
        )
        db.commit()
        cursor.close()
        db.close()

        return redirect('/products')

    cursor.close()
    db.close()
    return render_template("purchase.html", products=products, suppliers=suppliers)


@app.route('/purchase_history')
def purchase_history():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    query = """
    SELECT
        purchases.id,
        suppliers.name AS supplier,
        products.name AS product,
        purchases.quantity,
        purchases.cost,
        purchases.date
    FROM purchases
    JOIN suppliers ON purchases.supplier_id = suppliers.id
    JOIN products ON purchases.product_id = products.id
    ORDER BY purchases.id DESC
    """

    cursor.execute(query)
    data = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template("purchase_history.html", purchases=data)


print("TEMPLATE PATH:", template_dir)

if __name__ == "__main__":
    app.run(debug=True)
