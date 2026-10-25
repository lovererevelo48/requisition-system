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
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','department')),
            department TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS requisitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester TEXT NOT NULL,
            department TEXT NOT NULL,
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            justification TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK(status IN ('PENDING','APPROVED','REJECTED','FULFILLED')),
            created_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by TEXT
        )
    """)

    # Seed default admin
    cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users (username, password, role, department) VALUES (?,?,?,?)",
            ("admin", hash_password("admin123"), "admin", None),
        )

    conn.commit()
    conn.close()


# =========================================================
# DB QUERIES
# =========================================================
def db_login(username, password):
    row = get_db().execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, hash_password(password)),
    ).fetchone()
    return dict(row) if row else None


def db_register(username, password, role, department=None):
    try:
        cur = get_db()
        cur.execute(
            "INSERT INTO users (username, password, role, department) VALUES (?,?,?,?)",
            (username, hash_password(password), role, department),
        )
        cur.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def db_create_requisition(requester, department, item, qty, justification):
    db = get_db()
    db.execute(
        """INSERT INTO requisitions
           (requester, department, item, quantity, justification, status, created_at)
           VALUES (?,?,?,?,?, 'PENDING', ?)""",
        (requester, department, item, qty, justification,
         datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    db.commit()


def db_list_requisitions(department=None, status=None):
    q = "SELECT * FROM requisitions"
    clauses, params = [], []
    if department:
        clauses.append("department=?")
        params.append(department)
    if status:
        clauses.append("status=?")
        params.append(status)
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY id DESC"
    return [dict(r) for r in get_db().execute(q, params).fetchall()]


def db_get_requisition(req_id):
    row = get_db().execute("SELECT * FROM requisitions WHERE id=?", (req_id,)).fetchone()
    return dict(row) if row else None


def db_set_status(req_id, status, admin_username):
    db = get_db()
    db.execute(
        "UPDATE requisitions SET status=?, decided_at=?, decided_by=? WHERE id=?",
        (status, datetime.now().strftime("%Y-%m-%d %H:%M"), admin_username, req_id),
    )
    db.commit()


def db_stats(department=None):
    # Using reliable Python counting instead of SQLite COUNT
    reqs = db_list_requisitions(department=department)
    out = {"PENDING": 0, "APPROVED": 0, "REJECTED": 0, "FULFILLED": 0}
    for r in reqs:
        if r["status"] in out:
            out[r["status"]] += 1
    return out


# =========================================================
# AUTH DECORATORS
# =========================================================
def current_user():
    return session.get("user")


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        u = current_user()
        if not u or u["role"] != "admin":
            abort(403)
        return f(*a, **kw)
    return wrapper


# =========================================================
# BASE TEMPLATE
# =========================================================
BASE_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Requisition System{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  <style>
    body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; background:#f5f7fa; }
    .card { border-radius: .75rem; }
    .stat-card { transition: transform .15s ease, box-shadow .15s ease; border-left:4px solid transparent !important; }
    .stat-card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,.08) !important; }
    .stat-warning   { border-left-color:#ffc107 !important; }
    .stat-success   { border-left-color:#198754 !important; }
    .stat-danger    { border-left-color:#dc3545 !important; }
    .stat-primary   { border-left-color:#0d6efd !important; }
    .badge.status-pending   { background-color:#fff3cd; color:#664d03; }
    .badge.status-approved  { background-color:#d1e7dd; color:#0f5132; }
    .badge.status-rejected  { background-color:#f8d7da; color:#842029; }
    .badge.status-fulfilled { background-color:#cfe2ff; color:#084298; }
    .btn { border-radius:.5rem; }
    .btn i, .navbar-brand i, .badge i { vertical-align: middle; }
    .table thead th { font-size:.78rem; text-transform:uppercase; letter-spacing:.03em; color:#6c757d; }
    footer { font-size:.8rem; }
  </style>
</head>
<body>

<nav class="navbar navbar-expand-lg navbar-dark bg-primary shadow-sm">
  <div class="container">
    <a class="navbar-brand fw-bold" href="{{ url_for('dashboard') if user else url_for('login') }}">
      <i class="bi bi-clipboard-check"></i> Requisition System
    </a>
    <div class="ms-auto d-flex align-items-center">
      {% if user %}
        <span class="navbar-text me-3 text-white">
          <i class="bi bi-person-circle"></i> {{ user.username }}
          <span class="badge bg-light text-primary ms-1">{{ user.role }}</span>
        </span>
        {% if user.role == 'admin' %}
          <a href="{{ url_for('admin_requisitions') }}" class="btn btn-outline-light btn-sm me-1">
            <i class="bi bi-shield-check"></i> Admin
          </a>
        {% endif %}
        <a href="{{ url_for('dashboard') }}" class="btn btn-outline-light btn-sm me-1">
          <i class="bi bi-speedometer2"></i> Dashboard
        </a>
        <a href="{{ url_for('logout') }}" class="btn btn-light btn-sm">
          <i class="bi bi-box-arrow-right"></i> Logout
        </a>
      {% endif %}
    </div>
  </div>
</nav>

<div class="container py-4">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, msg in messages %}
      <div class="alert alert-{{ category }} alert-dismissible fade show shadow-sm">
        {{ msg }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endwith %}

  {% if error_title %}
    <div class="text-center py-5">
      <h1 class="display-5">{{ error_title }}</h1>
      <p class="text-muted">{{ error_msg }}</p>
      <a href="{{ url_for('dashboard') if user else url_for('login') }}" class="btn btn-primary">
        <i class="bi bi-house"></i> Go Home
      </a>
    </div>
  {% else %}
    {% block content %}{% endblock %}
  {% endif %}
</div>

<footer class="text-center text-muted small py-3">
  Requisition System &copy; 2026
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""


# =========================================================
# PAGE TEMPLATES
# =========================================================
LOGIN_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
<div class="row justify-content-center">
  <div class="col-md-5 col-lg-4">
    <div class="card shadow border-0 mt-5">
      <div class="card-body p-4">
        <h3 class="text-center mb-1">Welcome</h3>
        <p class="text-center text-muted mb-4">Sign in to continue</p>
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Username</label>
            <input type="text" name="username" class="form-control" required autofocus>
          </div>
          <div class="mb-3">
            <label class="form-label">Password</label>
            <input type="password" name="password" class="form-control" required>
          </div>
          <button class="btn btn-primary w-100">
            <i class="bi bi-box-arrow-in-right"></i> Sign in
          </button>
        </form>
        <p class="text-center small mt-3 mb-0">
          No account? <a href="{{ url_for('register') }}">Register here</a>
        </p>
      </div>
    </div>
    <p class="text-center text-muted small mt-3">Default admin: <code>admin / admin123</code></p>
  </div>
</div>
""")

REGISTER_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
<div class="row justify-content-center">
  <div class="col-md-6 col-lg-5">
    <div class="card shadow border-0 mt-4">
      <div class="card-body p-4">
        <h3 class="mb-3">Create account</h3>
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Username</label>
            <input type="text" name="username" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Password</label>
            <input type="password" name="password" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Role</label>
            <select name="role" id="role-select" class="form-select" required>
              <option value="department">Department user</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div class="mb-3" id="dept-group">
            <label class="form-label">Department</label>
            <input type="text" name="department" class="form-control" placeholder="e.g. IT, HR, Finance">
          </div>
          <button class="btn btn-success w-100">
            <i class="bi bi-person-plus"></i> Register
          </button>
        </form>
        <p class="text-center small mt-3 mb-0"><a href="{{ url_for('login') }}">Back to login</a></p>
      </div>
    </div>
  </div>
</div>
<script>
  const roleEl = document.getElementById('role-select');
  const deptGroup = document.getElementById('dept-group');
  function toggleDept(){ deptGroup.style.display = roleEl.value === 'department' ? '' : 'none'; }
  roleEl.addEventListener('change', toggleDept); toggleDept();
</script>
""")

DASHBOARD_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
<div class="d-flex justify-content-between align-items-center mb-4">
  <h2 class="mb-0"><i class="bi bi-speedometer2"></i> Dashboard</h2>
  {% if user.role == 'department' %}
    <a href="{{ url_for('new_requisition') }}" class="btn btn-primary">
      <i class="bi bi-plus-circle"></i> New Requisition
    </a>
  {% else %}
    <a href="{{ url_for('admin_requisitions') }}" class="btn btn-warning">
      <i class="bi bi-shield-check"></i> Manage Requisitions
    </a>
  {% endif %}
</div>

<div class="row g-3 mb-4">
  <div class="col-6 col-md-3">
    <div class="card border-0 shadow-sm stat-card stat-warning">
      <div class="card-body d-flex justify-content-between align-items-center">
        <div>
          <div class="text-uppercase small text-muted">PENDING</div>
          <div class="fs-3 fw-bold">{{ stats["PENDING"] }}</div>
        </div>
        <i class="bi bi-hourglass-split fs-1 opacity-50"></i>
      </div>
    </div>
  </div>
  
  <div class="col-6 col-md-3">
    <div class="card border-0 shadow-sm stat-card stat-success">
      <div class="card-body d-flex justify-content-between align-items-center">
        <div>
          <div class="text-uppercase small text-muted">APPROVED</div>
          <div class="fs-3 fw-bold">{{ stats["APPROVED"] }}</div>
        </div>
        <i class="bi bi-check-circle fs-1 opacity-50"></i>
      </div>
    </div>
  </div>

  <div class="col-6 col-md-3">
    <div class="card border-0 shadow-sm stat-card stat-danger">
      <div class="card-body d-flex justify-content-between align-items-center">
        <div>
          <div class="text-uppercase small text-muted">REJECTED</div>
          <div class="fs-3 fw-bold">{{ stats["REJECTED"] }}</div>
        </div>
        <i class="bi bi-x-circle fs-1 opacity-50"></i>
      </div>
    </div>
  </div>

  <div class="col-6 col-md-3">
    <div class="card border-0 shadow-sm stat-card stat-primary">
      <div class="card-body d-flex justify-content-between align-items-center">
        <div>
          <div class="text-uppercase small text-muted">FULFILLED</div>
          <div class="fs-3 fw-bold">{{ stats["FULFILLED"] }}</div>
        </div>
        <i class="bi bi-box-seam fs-1 opacity-50"></i>
      </div>
    </div>
  </div>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-header bg-white py-3">
    <h5 class="mb-0">
      <i class="bi bi-list-ul"></i>
      {% if user.role == 'department' %}My Requisitions{% else %}All Requisitions{% endif %}
    </h5>
  </div>
  <div class="table-responsive">
    <table class="table table-hover align-middle mb-0">
      <thead class="table-light">
        <tr>
          <th>#</th><th>Item</th><th>Qty</th>
          {% if user.role == 'admin' %}<th>Requester</th>{% endif %}
          <th>Department</th><th>Status</th><th>Created</th><th>Justification</th>
        </tr>
      </thead>
      <tbody>
        {% for r in requisitions %}
        <tr>
          <td class="text-muted">#{{ r.id }}</td>
          <td class="fw-semibold">{{ r.item }}</td>
          <td>{{ r.quantity }}</td>
          {% if user.role == 'admin' %}<td>{{ r.requester }}</td>{% endif %}
          <td><span class="badge bg-secondary">{{ r.department }}</span></td>
          <td><span class="badge status-{{ r.status|lower }}"><i class="bi bi-dot"></i>{{ r.status }}</span></td>
          <td class="text-muted small">{{ r.created_at }}</td>
          <td class="text-muted small">{{ r.justification or '—' }}</td>
        </tr>
        {% else %}
        <tr><td colspan="8" class="text-center text-muted py-4">
          <i class="bi bi-inbox fs-3 d-block mb-2"></i>No requisitions yet.
        </td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
""")

NEW_REQ_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
<div class="row justify-content-center">
  <div class="col-md-7 col-lg-6">
    <div class="card shadow border-0 mt-3">
      <div class="card-body p-4">
        <h3 class="mb-1"><i class="bi bi-plus-circle"></i> New Requisition</h3>
        <p class="text-muted">Department: <strong>{{ user.department }}</strong></p>
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Item</label>
            <input type="text" name="item" class="form-control" required autofocus>
          </div>
          <div class="mb-3">
            <label class="form-label">Quantity</label>
            <input type="number" name="quantity" min="1" class="form-control" required>
          </div>
          <div class="mb-3">
            <label class="form-label">Justification <span class="text-muted">(optional)</span></label>
            <textarea name="justification" rows="3" class="form-control"></textarea>
          </div>
          <div class="d-flex gap-2">
            <a href="{{ url_for('dashboard') }}" class="btn btn-outline-secondary">
              <i class="bi bi-arrow-left"></i> Cancel
            </a>
            <button class="btn btn-primary flex-grow-1">
              <i class="bi bi-send"></i> Submit
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>
""")

ADMIN_REQS_HTML = BASE_HTML.replace("{% block content %}{% endblock %}", """
<div class="d-flex justify-content-between align-items-center mb-4">
  <h2 class="mb-0"><i class="bi bi-shield-check"></i> Manage Requisitions</h2>
</div>

<div class="mb-3 d-flex flex-wrap gap-2">
  <a href="{{ url_for('admin_requisitions') }}"
     class="btn btn-sm {{ 'btn-primary' if not current_status else 'btn-outline-primary' }}">
    <i class="bi bi-list"></i> All
  </a>
  {% for st in ['PENDING','APPROVED','REJECTED','FULFILLED'] %}
    <a href="{{ url_for('admin_requisitions', status=st) }}"
       class="btn btn-sm {{ 'btn-primary' if current_status == st else 'btn-outline-primary' }}">
      {{ st }} ({{ stats[st] }})
    </a>
  {% endfor %}
</div>

<div class="card border-0 shadow-sm">
  <div class="table-responsive">
    <table class="table table-hover align-middle mb-0">
      <thead class="table-light">
        <tr>
          <th>#</th><th>Requester</th><th>Department</th>
          <th>Item</th><th>Qty</th><th>Status</th><th>Created</th>
          <th class="text-end">Actions</th>
        </tr>
      </thead>
      <tbody>
        {% for r in requisitions %}
        <tr>
          <td class="text-muted">#{{ r.id }}</td>
          <td>{{ r.requester }}</td>
          <td><span class="badge bg-secondary">{{ r.department }}</span></td>
          <td class="fw-semibold">{{ r.item }}</td>
          <td>{{ r.quantity }}</td>
          <td><span class="badge status-{{ r.status|lower }}"><i class="bi bi-dot"></i>{{ r.status }}</span></td>
          <td class="text-muted small">{{ r.created_at }}</td>
          <td class="text-end">
            {% if r.status == 'PENDING' %}
              <form method="post" class="d-inline"
                    action="{{ url_for('admin_action', req_id=r.id, action='approve') }}">
                <button class="btn btn-sm btn-success">
                  <i class="bi bi-check-lg"></i> Approve
                </button>
              </form>
              <form method="post" class="d-inline"
                    action="{{ url_for('admin_action', req_id=r.id, action='reject') }}">
                <button class="btn btn-sm btn-outline-danger">
                  <i class="bi bi-x-lg"></i> Reject
                </button>
              </form>
            {% elif r.status == 'APPROVED' %}
              <form method="post" class="d-inline"
                    action="{{ url_for('admin_action', req_id=r.id, action='fulfill') }}">
                <button class="btn btn-sm btn-primary">
                  <i class="bi bi-box-seam"></i> Fulfill
                </button>
              </form>
            {% else %}
              <span class="text-muted small">
                by {{ r.decided_by or '—' }}<br>{{ r.decided_at or '' }}
              </span>
            {% endif %}
          </td>
        </tr>
        {% else %}
        <tr><td colspan="8" class="text-center text-muted py-4">
          <i class="bi bi-inbox fs-3 d-block mb-2"></i>No requisitions found.
        </td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
""")


# =========================================================
# TEMPLATE CONTEXT
# =========================================================
@app.context_processor
def inject_user():
    return {"user": current_user()}


# =========================================================
# ROUTES
# =========================================================
@app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user() else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"]
        user = db_login(u, p)
        if user:
            session["user"] = user
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template_string(LOGIN_HTML)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]
        department = (request.form.get("department") or "").strip() or None
        if role == "department" and not department:
            flash("Department is required for department users.", "warning")
        elif db_register(username, password, role, department):
            flash("Account created — you can log in now.", "success")
            return redirect(url_for("login"))
        else:
            flash("Username already taken.", "danger")
    return render_template_string(REGISTER_HTML)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    u = current_user()
    scope = u["department"] if u["role"] == "department" else None
    reqs = db_list_requisitions(department=scope)
    s = db_stats(department=scope)
    return render_template_string(DASHBOARD_HTML, requisitions=reqs, stats=s)


@app.route("/requisition/new", methods=["GET", "POST"])
@login_required
def new_requisition():
    u = current_user()
    if u["role"] != "department":
        flash("Only department users can create requisitions.", "warning")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        item = request.form["item"].strip()
        try:
            qty = int(request.form["quantity"])
        except ValueError:
            flash("Quantity must be a number.", "danger")
            return redirect(url_for("new_requisition"))
        justification = request.form.get("justification", "").strip()
        if not item or qty <= 0:
            flash("Please provide a valid item and quantity.", "danger")
        else:
            db_create_requisition(u["username"], u["department"], item, qty, justification)
            flash("Requisition submitted.", "success")
            return redirect(url_for("dashboard"))
    return render_template_string(NEW_REQ_HTML)


@app.route("/admin/requisitions")
@admin_required
def admin_requisitions():
    status = request.args.get("status") or None
    reqs = db_list_requisitions(status=status)
    s = db_stats()
    return render_template_string(
        ADMIN_REQS_HTML, requisitions=reqs, stats=s, current_status=status
    )


@app.route("/admin/requisitions/<int:req_id>/<action>", methods=["POST"])
@admin_required
def admin_action(req_id, action):
    u = current_user()
    if action == "approve":
        db_set_status(req_id, "APPROVED", u["username"])
        flash(f"Requisition #{req_id} approved.", "success")
    elif action == "reject":
        db_set_status(req_id, "REJECTED", u["username"])
        flash(f"Requisition #{req_id} rejected.", "danger")
    elif action == "fulfill":
        req = db_get_requisition(req_id)
        if req and req["status"] == "APPROVED":
            db_set_status(req_id, "FULFILLED", u["username"])
            flash(f"Requisition #{req_id} fulfilled.", "primary")
        else:
            flash("Only approved requisitions can be fulfilled.", "warning")
    else:
        abort(400)
    return redirect(request.referrer or url_for("admin_requisitions"))


# =========================================================
# ERROR HANDLERS
# =========================================================
@app.errorhandler(403)
def forbidden(_):
    return render_template_string(
        BASE_HTML, error_title="403 — Forbidden",
        error_msg="You don't have permission to view this page."
    ), 403


@app.errorhandler(404)
def not_found(_):
    return render_template_string(
        BASE_HTML, error_title="404 — Not Found",
        error_msg="The page you're looking for doesn't exist."
    ), 404


# =========================================================
# MAIN
# =========================================================
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
