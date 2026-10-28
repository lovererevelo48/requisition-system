"""
Complete Requisition System — single-file Flask app.
Run:  python app.py
Open: http://127.0.0.1:5000
Default admin: admin / admin123
"""
import sqlite3
import hashlib
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, redirect, url_for, session, flash,
    render_template_string, abort, g
)

# =========================================================
# CONFIG
# =========================================================
DB_FILE = "requisitions.db"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

app = Flask(__name__)
app.secret_key = SECRET_KEY


# =========================================================
# DATABASE HELPERS
# =========================================================
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    db = sqlite3.connect(DB_FILE)
    cur = db.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            department TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS requisitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            quantity INTEGER NOT NULL DEFAULT 1,
            department TEXT DEFAULT '',
            requested_by TEXT DEFAULT '',
            priority TEXT DEFAULT 'Normal',
            status TEXT DEFAULT 'Pending',
            created_at TEXT NOT NULL
        )
    """)

    # Default admin
    cur.execute("SELECT * FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password, role, department) VALUES (?, ?, ?, ?)",
            ("admin", hash_password("admin123"), "admin", "Administration"),
        )

    db.commit()
    db.close()


# =========================================================
# AUTH HELPERS
# =========================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# =========================================================
# TEMPLATES
# =========================================================
BASE_TEMPLATE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Requisition System</title>
<style>
    body { font-family: Arial, Helvetica, sans-serif; margin: 0; background: #f4f6f8; color: #222; }
    nav { background: #2c3e50; padding: 12px 20px; display: flex; gap: 18px; align-items: center; }
    nav a { color: #fff; text-decoration: none; padding: 6px 10px; border-radius: 4px; }
    nav a:hover { background: #34495e; }
    nav .spacer { flex: 1; }
    .container { max-width: 1200px; margin: 20px auto; padding: 0 20px; }
    .flash { padding: 10px 14px; border-radius: 4px; margin-bottom: 10px; }
    .flash.success { background: #d4edda; color: #155724; }
    .flash.warning { background: #fff3cd; color: #856404; }
    .flash.danger { background: #f8d7da; color: #721c24; }
    table { width: 100%; border-collapse: collapse; background: #fff; }
    th, td { padding: 8px 10px; border-bottom: 1px solid #e0e0e0; text-align: left; font-size: 14px; }
    th { background: #ecf0f1; }
    input, select, textarea { padding: 7px 9px; border: 1px solid #bbb; border-radius: 4px; font-size: 14px; box-sizing: border-box; }
    button { padding: 8px 14px; border: none; border-radius: 4px; background: #2980b9; color: #fff; cursor: pointer; font-size: 14px; }
    button:hover { background: #216a94; }
    button.secondary { background: #7f8c8d; }
    button.danger { background: #c0392b; }
    .filter-bar { background: #fff; padding: 14px; border-radius: 6px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    .filter-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; align-items: end; }
    .filter-grid label { display: block; font-size: 12px; font-weight: bold; color: #555; margin-bottom: 3px; }
    .filter-grid input, .filter-grid select { width: 100%; }
    .actions { display: flex; gap: 6px; flex-wrap: wrap; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold; }
    .badge.Pending { background: #fef3c7; color: #92400e; }
    .badge.Approved { background: #d1fae5; color: #065f46; }
    .badge.Rejected { background: #fee2e2; color: #991b1b; }
    .badge.Normal { background: #e5e7eb; color: #374151; }
    .badge.High { background: #ffedd5; color: #9a3412; }
    .badge.Urgent { background: #fee2e2; color: #b91c1c; }
    .result-count { font-size: 13px; color: #666; margin-bottom: 8px; }
</style>
</head>
<body>
<nav>
    <a href="{{ url_for('index') }}">Requisitions</a>
    {% if session.get('role') == 'admin' %}
    <a href="{{ url_for('users') }}">Users</a>
    {% endif %}
    <span class="spacer"></span>
    {% if session.get('username') %}
        <span style="color:#bdc3c7;">Signed in as <b>{{ session.username }}</b></span>
        <a href="{{ url_for('logout') }}">Logout</a>
    {% else %}
        <a href="{{ url_for('login') }}">Login</a>
    {% endif %}
</nav>
<div class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}
        <div class="flash {{ cat }}">{{ msg }}</div>
      {% endfor %}
    {% endwith %}
    {% block content %}{% endblock %}
</div>
</body>
</html>
"""

LOGIN_TEMPLATE = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", """
{% block content %}
<h2>Login</h2>
<form method="post" style="max-width:320px;">
    <label>Username</label><br>
    <input name="username" required style="width:100%;"><br><br>
    <label>Password</label><br>
    <input name="password" type="password" required style="width:100%;"><br><br>
    <button type="submit">Sign In</button>
</form>
<p style="color:#777;font-size:13px;">Default: <b>admin / admin123</b></p>
{% endblock %}
""")

INDEX_TEMPLATE = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", """
{% block content %}
<h2>Requisitions</h2>

<form method="get" class="filter-bar">
    <div class="filter-grid">
        <div>
            <label>Item Name</label>
            <input name="f_item" value="{{ f.item }}" placeholder="Search item name…">
        </div>
        <div>
            <label>Description</label>
            <input name="f_desc" value="{{ f.desc }}" placeholder="Search description…">
        </div>
        <div>
            <label>Department</label>
            <select name="f_dept">
                <option value="">All departments</option>
                {% for d in options.departments %}
                <option value="{{ d }}" {% if f.dept == d %}selected{% endif %}>{{ d }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label>Requested By</label>
            <select name="f_requester">
                <option value="">All requesters</option>
                {% for r in options.requesters %}
                <option value="{{ r }}" {% if f.requester == r %}selected{% endif %}>{{ r }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label>Status</label>
            <select name="f_status">
                <option value="">All statuses</option>
                {% for s in options.statuses %}
                <option value="{{ s }}" {% if f.status == s %}selected{% endif %}>{{ s }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label>Priority</label>
            <select name="f_priority">
                <option value="">All priorities</option>
                {% for p in options.priorities %}
                <option value="{{ p }}" {% if f.priority == p %}selected{% endif %}>{{ p }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label>Min Qty</label>
            <input name="f_qty_min" type="number" min="0" value="{{ f.qty_min }}">
        </div>
        <div>
            <label>Max Qty</label>
            <input name="f_qty_max" type="number" min="0" value="{{ f.qty_max }}">
        </div>
        <div>
            <label>Created From</label>
            <input name="f_date_from" type="date" value="{{ f.date_from }}">
        </div>
        <div>
            <label>Created To</label>
            <input name="f_date_to" type="date" value="{{ f.date_to }}">
        </div>
        <div>
            <label>Sort By</label>
            <select name="sort">
                {% for key, label in sort_options %}
                <option value="{{ key }}" {% if f.sort == key %}selected{% endif %}>{{ label }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <label>Order</label>
            <select name="order">
                <option value="asc" {% if f.order == 'asc' %}selected{% endif %}>Ascending</option>
                <option value="desc" {% if f.order == 'desc' %}selected{% endif %}>Descending</option>
            </select>
        </div>
        <div style="display:flex;gap:6px;">
            <button type="submit">Filter</button>
            <a href="{{ url_for('index') }}" style="text-decoration:none;"><button type="button" class="secondary">Reset</button></a>
        </div>
    </div>
</form>

<div class="result-count">
    Showing <b>{{ requisitions|length }}</b> result(s)
    {% if has_filters %}(filters applied){% endif %}
</div>

{% if session.get('role') == 'admin' or session.get('user_id') %}
<p>
    <a href="{{ url_for('add_requisition') }}"><button>+ New Requisition</button></a>
</p>
{% endif %}

<table>
    <thead>
        <tr>
            <th>#</th>
            <th>Item</th>
            <th>Description</th>
            <th>Qty</th>
            <th>Department</th>
            <th>Requested By</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Created</th>
            <th>Actions</th>
        </tr>
    </thead>
    <tbody>
    {% for r in requisitions %}
        <tr>
            <td>{{ r.id }}</td>
            <td>{{ r.item_name }}</td>
            <td>{{ r.description }}</td>
            <td>{{ r.quantity }}</td>
            <td>{{ r.department }}</td>
            <td>{{ r.requested_by }}</td>
            <td><span class="badge {{ r.priority }}">{{ r.priority }}</span></td>
            <td><span class="badge {{ r.status }}">{{ r.status }}</span></td>
            <td>{{ r.created_at }}</td>
            <td>
                <div class="actions">
                    <a href="{{ url_for('edit_requisition', req_id=r.id) }}"><button class="secondary">Edit</button></a>
                    {% if session.get('role') == 'admin' %}
                    <form method="post" action="{{ url_for('delete_requisition', req_id=r.id) }}" onsubmit="return confirm('Delete this requisition?');">
                        <button class="danger">Delete</button>
                    </form>
                    {% endif %}
                </div>
            </td>
        </tr>
    {% else %}
        <tr><td colspan="10" style="text-align:center;color:#888;">No requisitions found.</td></tr>
    {% endfor %}
    </tbody>
</table>
{% endblock %}
""")

FORM_TEMPLATE = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", """
{% block content %}
<h2>{{ 'Edit' if req else 'New' }} Requisition</h2>
<form method="post" style="max-width:600px;background:#fff;padding:20px;border-radius:6px;">
    <label>Item Name *</label><br>
    <input name="item_name" required style="width:100%;" value="{{ req.item_name if req else '' }}"><br><br>

    <label>Description</label><br>
    <textarea name="description" rows="3" style="width:100%;">{{ req.description if req else '' }}</textarea><br><br>

    <label>Quantity *</label><br>
    <input name="quantity" type="number" min="1" required style="width:100%;" value="{{ req.quantity if req else 1 }}"><br><br>

    <label>Department</label><br>
    <input name="department" style="width:100%;" value="{{ req.department if req else '' }}"><br><br>

    <label>Requested By</label><br>
    <input name="requested_by" style="width:100%;" value="{{ req.requested_by if req else session.get('username','') }}"><br><br>

    <label>Priority</label><br>
    <select name="priority" style="width:100%;">
        {% for p in ['Normal','High','Urgent'] %}
        <option value="{{ p }}" {% if req and req.priority == p %}selected{% endif %}>{{ p }}</option>
        {% endfor %}
    </select><br><br>

    <label>Status</label><br>
    <select name="status" style="width:100%;">
        {% for s in ['Pending','Approved','Rejected'] %}
        <option value="{{ s }}" {% if req and req.status == s %}selected{% endif %}>{{ s }}</option>
        {% endfor %}
    </select><br><br>

    <button type="submit">Save</button>
    <a href="{{ url_for('index') }}"><button type="button" class="secondary">Cancel</button></a>
</form>
{% endblock %}
""")

USERS_TEMPLATE = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", """
{% block content %}
<h2>Users</h2>
<form method="post" action="{{ url_for('add_user') }}" style="background:#fff;padding:16px;border-radius:6px;margin-bottom:16px;">
    <div class="filter-grid">
        <div><label>Username</label><input name="username" required></div>
        <div><label>Password</label><input name="password" type="password" required></div>
        <div><label>Role</label>
            <select name="role"><option value="user">user</option><option value="admin">admin</option></select>
        </div>
        <div><label>Department</label><input name="department"></div>
        <div><button type="submit">Add User</button></div>
    </div>
</form>

<table>
    <thead><tr><th>ID</th><th>Username</th><th>Role</th><th>Department</th><th>Actions</th></tr></thead>
    <tbody>
    {% for u in users %}
        <tr>
            <td>{{ u.id }}</td>
            <td>{{ u.username }}</td>
            <td>{{ u.role }}</td>
            <td>{{ u.department }}</td>
            <td>
                {% if u.username != 'admin' %}
                <form method="post" action="{{ url_for('delete_user', user_id=u.id) }}" onsubmit="return confirm('Delete user?');">
                    <button class="danger">Delete</button>
                </form>
                {% endif %}
            </td>
        </tr>
    {% endfor %}
    </tbody>
</table>
{% endblock %}
""")


# =========================================================
# ROUTES
# =========================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and user["password"] == hash_password(password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash(f"Welcome, {user['username']}!", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password.", "danger")
    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    db = get_db()

    # ---- Read filter params ----
    f = {
        "item": request.args.get("f_item", "").strip(),
        "desc": request.args.get("f_desc", "").strip(),
        "dept": request.args.get("f_dept", "").strip(),
        "requester": request.args.get("f_requester", "").strip(),
        "status": request.args.get("f_status", "").strip(),
        "priority": request.args.get("f_priority", "").strip(),
        "qty_min": request.args.get("f_qty_min", "").strip(),
        "qty_max": request.args.get("f_qty_max", "").strip(),
        "date_from": request.args.get("f_date_from", "").strip(),
        "date_to": request.args.get("f_date_to", "").strip(),
        "sort": request.args.get("sort", "created_at"),
        "order": request.args.get("order", "desc"),
    }

    # ---- Build WHERE clause dynamically ----
    where, params = [], []

    if f["item"]:
        where.append("LOWER(item_name) LIKE ?")
        params.append(f"%{f['item'].lower()}%")
    if f["desc"]:
        where.append("LOWER(description) LIKE ?")
        params.append(f"%{f['desc'].lower()}%")
    if f["dept"]:
        where.append("department = ?")
        params.append(f["dept"])
    if f["requester"]:
        where.append("requested_by = ?")
        params.append(f["requester"])
    if f["status"]:
        where.append("status = ?")
        params.append(f["status"])
    if f["priority"]:
        where.append("priority = ?")
        params.append(f["priority"])
    if f["qty_min"]:
        try:
            where.append("quantity >= ?")
            params.append(int(f["qty_min"]))
        except ValueError:
            pass
    if f["qty_max"]:
        try:
            where.append("quantity <= ?")
            params.append(int(f["qty_max"]))
        except ValueError:
            pass
    if f["date_from"]:
        where.append("DATE(created_at) >= DATE(?)")
        params.append(f["date_from"])
    if f["date_to"]:
        where.append("DATE(created_at) <= DATE(?)")
        params.append(f["date_to"])

    # ---- Whitelist sort columns ----
    sort_columns = {
        "id": "id",
        "item_name": "item_name",
        "quantity": "quantity",
        "department": "department",
        "requested_by": "requested_by",
        "priority": "priority",
        "status": "status",
        "created_at": "created_at",
    }
    sort_col = sort_columns.get(f["sort"], "created_at")
    order = "ASC" if f["order"].lower() == "asc" else "DESC"

    sql = "SELECT * FROM requisitions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {sort_col} {order}"

    requisitions = db.execute(sql, params).fetchall()

    # ---- Build dropdown options from existing data ----
    options = {
        "departments": [row["department"] for row in
                        db.execute("SELECT DISTINCT department FROM requisitions WHERE department != '' ORDER BY department")],
        "requesters": [row["requested_by"] for row in
                       db.execute("SELECT DISTINCT requested_by FROM requisitions WHERE requested_by != '' ORDER BY requested_by")],
        "statuses": ["Pending", "Approved", "Rejected"],
        "priorities": ["Normal", "High", "Urgent"],
    }

    sort_options = [
        ("created_at", "Date Created"),
        ("item_name", "Item Name"),
        ("quantity", "Quantity"),
        ("department", "Department"),
        ("requested_by", "Requested By"),
        ("priority", "Priority"),
        ("status", "Status"),
        ("id", "ID"),
    ]

    has_filters = any([f["item"], f["desc"], f["dept"], f["requester"],
                       f["status"], f["priority"], f["qty_min"], f["qty_max"],
                       f["date_from"], f["date_to"]])

    return render_template_string(
        INDEX_TEMPLATE,
        requisitions=requisitions,
        f=f,
        options=options,
        sort_options=sort_options,
        has_filters=has_filters,
    )


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_requisition():
    if request.method == "POST":
        db = get_db()
        db.execute("""
            INSERT INTO requisitions
            (item_name, description, quantity, department, requested_by, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["item_name"].strip(),
            request.form.get("description", "").strip(),
            int(request.form.get("quantity", 1)),
            request.form.get("department", "").strip(),
            request.form.get("requested_by", "").strip(),
            request.form.get("priority", "Normal"),
            request.form.get("status", "Pending"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        db.commit()
        flash("Requisition created.", "success")
        return redirect(url_for("index"))
    return render_template_string(FORM_TEMPLATE, req=None)


@app.route("/edit/<int:req_id>", methods=["GET", "POST"])
@login_required
def edit_requisition(req_id):
    db = get_db()
    req = db.execute("SELECT * FROM requisitions WHERE id = ?", (req_id,)).fetchone()
    if not req:
        abort(404)

    if request.method == "POST":
        db.execute("""
            UPDATE requisitions
            SET item_name=?, description=?, quantity=?, department=?,
                requested_by=?, priority=?, status=?
            WHERE id=?
        """, (
            request.form["item_name"].strip(),
            request.form.get("description", "").strip(),
            int(request.form.get("quantity", 1)),
            request.form.get("department", "").strip(),
            request.form.get("requested_by", "").strip(),
            request.form.get("priority", "Normal"),
            request.form.get("status", "Pending"),
            req_id,
        ))
        db.commit()
        flash("Requisition updated.", "success")
        return redirect(url_for("index"))

    return render_template_string(FORM_TEMPLATE, req=req)


@app.route("/delete/<int:req_id>", methods=["POST"])
@login_required
@admin_required
def delete_requisition(req_id):
    db = get_db()
    db.execute("DELETE FROM requisitions WHERE id = ?", (req_id,))
    db.commit()
    flash("Requisition deleted.", "success")
    return redirect(url_for("index"))


# =========================================================
# USERS (admin only)
# =========================================================
@app.route("/users")
@login_required
@admin_required
def users():
    db = get_db()
    all_users = db.execute("SELECT * FROM users ORDER BY username").fetchall()
    return render_template_string(USERS_TEMPLATE, users=all_users)


@app.route("/users/add", methods=["POST"])
@login_required
@admin_required
def add_user():
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password, role, department) VALUES (?, ?, ?, ?)",
            (
                request.form["username"].strip(),
                hash_password(request.form["password"]),
                request.form.get("role", "user"),
                request.form.get("department", "").strip(),
            ),
        )
        db.commit()
        flash("User added.", "success")
    except sqlite3.IntegrityError:
        flash("Username already exists.", "danger")
    return redirect(url_for("users"))


@app.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ? AND username != 'admin'", (user_id,))
    db.commit()
    flash("User deleted.", "success")
    return redirect(url_for("users"))


# =========================================================
# MAIN
# =========================================================
# Initialize the database when the app starts (works on Render & local)
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
