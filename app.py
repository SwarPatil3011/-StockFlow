import mysql.connector
import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.getenv("DB_PASSWORD"),
        database="stockflow_db"
    )

def admin_required():
    if 'user' not in session:
        return redirect('/login')
    if session.get('role') != 'admin':
        return redirect('/access_denied')
    return None

base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")

app = Flask(__name__, template_folder=template_dir)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# Secret key (used .env)
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(24)

# Session settings
app.permanent_session_lifetime = timedelta(minutes=30)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,   # True in production (HTTPS)
    SESSION_COOKIE_SAMESITE='Lax'
)

@app.route("/")
def home():
    return redirect('/login')

@app.route('/access_denied')
def access_denied():
    return render_template('access_denied.html')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect('/dashboard')

    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor(dictionary=True, buffered=True)

        username = request.form["username"]
        entered_password = request.form["password"]

        cursor.execute(
            "SELECT * FROM users WHERE username=%s",
            (username,)
        )

        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and check_password_hash(user['password'], entered_password):
            session['user'] = username
            session['role'] = user['role']
            # Redirect based on role
            if user['role'] == 'admin':
                return redirect('/dashboard')
            else:
                return redirect('/products')
        else:
            return render_template("login.html", error="Wrong username or password")

    return render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register():
    check = admin_required()
    if check: return check
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor(dictionary=True, buffered=True)

        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Check passwords match
        if password != confirm_password:
            cursor.close()
            db.close()
            return render_template("register.html", error="Passwords do not match")

        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing = cursor.fetchone()

        if existing:
            cursor.close()
            db.close()
            return render_template("register.html", error="Username already taken")

        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hashed_password)
        )
        db.commit()
        cursor.close()
        db.close()

        return redirect('/login')

    return render_template("register.html")

@app.route('/users')
def manage_users():
    check = admin_required()
    if check: return check

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT id, username, role FROM users ORDER BY id ASC")
    users = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('users.html', users=users)


@app.route('/add_user', methods=['POST'])
def add_user():
    check = admin_required()
    if check: return check

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    username = request.form['username'].strip()
    password = request.form['password']
    role = request.form['role']

    # Check if username already exists
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("SELECT id, username, role FROM users ORDER BY id ASC")
        users = cursor.fetchall()
        cursor.close()
        db.close()
        return render_template('users.html', users=users, error="Username already taken")

    hashed_password = generate_password_hash(password)
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
        (username, hashed_password, role)
    )
    db.commit()

    cursor.execute("SELECT id, username, role FROM users ORDER BY id ASC")
    users = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('users.html', users=users, success=f"User '{username}' created successfully!")


@app.route('/delete_user/<int:id>', methods=['POST'])
def delete_user(id):
    check = admin_required()
    if check: return check

    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM users WHERE id=%s", (id,))
    db.commit()
    cursor.close()
    db.close()

    return redirect('/users')

@app.route('/dashboard')
def dashboard():
    check = admin_required()
    if check is not None:
        return check

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
        SELECT products.name, SUM(bill_items.quantity) AS total_sold
        FROM bill_items
        JOIN products ON bill_items.product_id = products.id
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
    session.clear()  # Clear all session data
    return redirect('/login')


# ── REPLACE these 4 routes in app.py ──

@app.route("/products")
def products():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("SELECT * FROM categories ORDER BY name ASC")
    categories = cursor.fetchall()

    cursor.execute("SELECT * FROM suppliers ORDER BY name ASC")
    suppliers = cursor.fetchall()

    selected_category = request.args.get("category")
    search = request.args.get("search")

    query = """
        SELECT products.*,
               categories.name AS category_name,
               suppliers.name AS supplier_name
        FROM products
        LEFT JOIN categories ON products.category_id = categories.id
        LEFT JOIN suppliers ON products.supplier_id = suppliers.id
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

    selected_category = int(selected_category) if selected_category else None

    return render_template("products.html",
        products=product_list,
        categories=categories,
        suppliers=suppliers,
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
    supplier_id = request.form.get("supplier_id") or None

    cursor.execute(
        "INSERT INTO products (name, price, quantity, category_id, supplier_id) VALUES (%s, %s, %s, %s, %s)",
        (name, price, quantity, category_id, supplier_id)
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

    cursor.execute("SELECT * FROM suppliers ORDER BY name ASC")
    suppliers = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template("edit_product.html", product=product, categories=categories, suppliers=suppliers)


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
    supplier_id = request.form.get("supplier_id") or None

    cursor.execute(
        "UPDATE products SET name=%s, price=%s, quantity=%s, category_id=%s, supplier_id=%s WHERE id=%s",
        (name, price, quantity, category_id, supplier_id, id)
    )
    db.commit()
    cursor.close()
    db.close()

    return redirect("/products")

@app.route("/categories")
def categories():
    check = admin_required()
    if check is not None:
        return check

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
    check = admin_required()
    if check is not None:
        return check

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
    check = admin_required()
    if check is not None:
        return check

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
    cursor.execute("SELECT * FROM products ORDER BY name ASC")
    products = cursor.fetchall()

    message = None

    if request.method == 'POST':
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')

        if not product_ids or not any(pid for pid in product_ids):
            message = "Please select at least one product"
            cursor.close()
            db.close()
            return render_template('billing.html', products=products, message=message)

        grand_total = 0
        items = []

        # Validate all items first
        for i in range(len(product_ids)):
            product_id = product_ids[i]
            quantity = int(quantities[i]) if quantities[i] else 0

            if not product_id or quantity <= 0:
                continue

            cursor.execute("SELECT * FROM products WHERE id=%s", (product_id,))
            product = cursor.fetchone()

            if not product:
                message = f"Product not found"
                cursor.close()
                db.close()
                return render_template('billing.html', products=products, message=message)

            if quantity > product['quantity']:
                message = f"Not enough stock for {product['name']}! Available: {product['quantity']}"
                cursor.close()
                db.close()
                return render_template('billing.html', products=products, message=message)

            subtotal = product['price'] * quantity
            grand_total += subtotal
            items.append({
                'product_id': product_id,
                'quantity': quantity,
                'price': product['price'],
                'subtotal': subtotal,
                'current_stock': product['quantity']
            })

        if not items:
            message = "Please add at least one valid item"
            cursor.close()
            db.close()
            return render_template('billing.html', products=products, message=message)

        # Create bill
        cursor.execute(
            "INSERT INTO bills (total) VALUES (%s)",
            (grand_total,)
        )
        bill_id = cursor.lastrowid

        # Insert bill items and update stock
        for item in items:
            cursor.execute(
                "INSERT INTO bill_items (bill_id, product_id, quantity, price, subtotal) VALUES (%s, %s, %s, %s, %s)",
                (bill_id, item['product_id'], item['quantity'], item['price'], item['subtotal'])
            )
            new_stock = item['current_stock'] - item['quantity']
            cursor.execute(
                "UPDATE products SET quantity=%s WHERE id=%s",
                (new_stock, item['product_id'])
            )

        db.commit()
        cursor.close()
        db.close()

        return redirect(f"/invoice/{bill_id}")

    cursor.close()
    db.close()
    return render_template('billing.html', products=products, message=message)


@app.route('/bills')
def bills():
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    query = """
    SELECT
        bills.id,
        bills.total,
        bills.date,
        COUNT(bill_items.id) AS item_count
    FROM bills
    LEFT JOIN bill_items ON bills.id = bill_items.bill_id
    GROUP BY bills.id, bills.total, bills.date
    ORDER BY bills.id DESC
    """

    cursor.execute(query)
    all_bills = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('bills.html', bills=all_bills)


@app.route('/invoice/<int:bill_id>')
def invoice(bill_id):
    if 'user' not in session:
        return redirect('/login')

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    # Get bill info
    cursor.execute("SELECT * FROM bills WHERE id=%s", (bill_id,))
    bill = cursor.fetchone()

    # Get bill items
    cursor.execute("""
        SELECT bill_items.*, products.name AS product_name
        FROM bill_items
        JOIN products ON bill_items.product_id = products.id
        WHERE bill_items.bill_id = %s
    """, (bill_id,))
    items = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template('invoice.html', bill=bill, items=items)


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
    check = admin_required()
    if check is not None:
        return check

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
    check = admin_required()
    if check is not None:
        return check

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


@app.route('/suppliers')
def suppliers():
    check = admin_required()
    if check: return check

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute("""
        SELECT suppliers.id, suppliers.name, suppliers.phone,
               COUNT(products.id) AS product_count
        FROM suppliers
        LEFT JOIN products ON products.supplier_id = suppliers.id
        GROUP BY suppliers.id, suppliers.name, suppliers.phone
        ORDER BY suppliers.name ASC
    """)
    all_suppliers = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('suppliers.html', suppliers=all_suppliers)


@app.route('/add_supplier', methods=['POST'])
def add_supplier():
    check = admin_required()
    if check: return check

    db = get_db()
    cursor = db.cursor(dictionary=True, buffered=True)

    name = request.form['name'].strip()
    phone = request.form.get('phone', '').strip()

    # Check duplicate
    cursor.execute("SELECT * FROM suppliers WHERE name=%s", (name,))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            SELECT suppliers.id, suppliers.name, suppliers.phone,
                   COUNT(products.id) AS product_count
            FROM suppliers
            LEFT JOIN products ON products.supplier_id = suppliers.id
            GROUP BY suppliers.id, suppliers.name, suppliers.phone
            ORDER BY suppliers.name ASC
        """)
        all_suppliers = cursor.fetchall()
        cursor.close()
        db.close()
        return render_template('suppliers.html', suppliers=all_suppliers, error="Supplier already exists")

    cursor.execute(
        "INSERT INTO suppliers (name, phone) VALUES (%s, %s)",
        (name, phone or None)
    )
    db.commit()

    cursor.execute("""
        SELECT suppliers.id, suppliers.name, suppliers.phone,
               COUNT(products.id) AS product_count
        FROM suppliers
        LEFT JOIN products ON products.supplier_id = suppliers.id
        GROUP BY suppliers.id, suppliers.name, suppliers.phone
        ORDER BY suppliers.name ASC
    """)
    all_suppliers = cursor.fetchall()
    cursor.close()
    db.close()

    return render_template('suppliers.html', suppliers=all_suppliers, success=f"Supplier '{name}' added!")


@app.route('/edit_supplier/<int:id>', methods=['POST'])
def edit_supplier(id):
    check = admin_required()
    if check: return check

    db = get_db()
    cursor = db.cursor()

    name = request.form['name'].strip()
    phone = request.form.get('phone', '').strip()

    cursor.execute(
        "UPDATE suppliers SET name=%s, phone=%s WHERE id=%s",
        (name, phone or None, id)
    )
    db.commit()
    cursor.close()
    db.close()

    return redirect('/suppliers')


@app.route('/delete_supplier/<int:id>', methods=['POST'])
def delete_supplier(id):
    check = admin_required()
    if check: return check

    db = get_db()
    cursor = db.cursor()

    # Set supplier_id to NULL for products using this supplier
    cursor.execute("UPDATE products SET supplier_id = NULL WHERE supplier_id = %s", (id,))
    cursor.execute("DELETE FROM suppliers WHERE id = %s", (id,))
    db.commit()
    cursor.close()
    db.close()

    return redirect('/suppliers')

if __name__ == "__main__":
    app.run(debug=True)
