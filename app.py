import hmac
import os
import secrets
import sqlite3
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, session, url_for)

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SMS_DB", os.path.join(BASE, "students.db"))
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    dept TEXT,
    year INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    credits INTEGER DEFAULT 3
);
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    grade TEXT DEFAULT '',
    UNIQUE(student_id, course_id)
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


init_db()


# ---------- auth + csrf ----------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf", "")
        if not hmac.compare_digest(sent, session.get("csrf", "x")):
            abort(400, "Invalid CSRF token")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if hmac.compare_digest(u, ADMIN_USER) and hmac.compare_digest(p, ADMIN_PASS):
            session.clear()
            session["user"] = u
            return redirect(url_for("dashboard"))
        flash("Invalid username or password", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/health")
def health():
    return "ok"


# ---------- dashboard ----------
@app.route("/")
@login_required
def dashboard():
    db = get_db()
    stats = {
        "students": db.execute("SELECT COUNT(*) FROM students").fetchone()[0],
        "courses": db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "enrollments": db.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0],
    }
    by_dept = db.execute(
        "SELECT COALESCE(NULLIF(dept,''),'Unassigned') d, COUNT(*) n "
        "FROM students GROUP BY d ORDER BY n DESC").fetchall()
    recent = db.execute(
        "SELECT * FROM students ORDER BY id DESC LIMIT 5").fetchall()
    return render_template("dashboard.html", stats=stats, by_dept=by_dept, recent=recent)


# ---------- students ----------
@app.route("/students")
@login_required
def students():
    q = request.args.get("q", "").strip()
    db = get_db()
    if q:
        like = f"%{q}%"
        rows = db.execute(
            "SELECT * FROM students WHERE name LIKE ? OR roll_no LIKE ? "
            "OR dept LIKE ? OR email LIKE ? ORDER BY roll_no",
            (like, like, like, like)).fetchall()
    else:
        rows = db.execute("SELECT * FROM students ORDER BY roll_no").fetchall()
    return render_template("students.html", students=rows, q=q)


def _student_form():
    f = request.form
    return (f.get("roll_no", "").strip(), f.get("name", "").strip(),
            f.get("email", "").strip(), f.get("phone", "").strip(),
            f.get("dept", "").strip(), int(f.get("year") or 1))


@app.route("/students/new", methods=["GET", "POST"])
@login_required
def student_new():
    if request.method == "POST":
        data = _student_form()
        if not data[0] or not data[1]:
            flash("Roll number and name are required", "error")
        else:
            try:
                db = get_db()
                db.execute("INSERT INTO students(roll_no,name,email,phone,dept,year) "
                           "VALUES (?,?,?,?,?,?)", data)
                db.commit()
                flash("Student added", "ok")
                return redirect(url_for("students"))
            except sqlite3.IntegrityError:
                flash("That roll number already exists", "error")
    return render_template("student_form.html", s=None)


@app.route("/students/<int:sid>")
@login_required
def student_detail(sid):
    db = get_db()
    s = db.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    if not s:
        abort(404)
    enr = db.execute(
        "SELECT e.id, e.grade, c.code, c.title, c.credits FROM enrollments e "
        "JOIN courses c ON c.id=e.course_id WHERE e.student_id=? ORDER BY c.code",
        (sid,)).fetchall()
    available = db.execute(
        "SELECT * FROM courses WHERE id NOT IN "
        "(SELECT course_id FROM enrollments WHERE student_id=?) ORDER BY code",
        (sid,)).fetchall()
    return render_template("student_detail.html", s=s, enr=enr, available=available)


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def student_edit(sid):
    db = get_db()
    s = db.execute("SELECT * FROM students WHERE id=?", (sid,)).fetchone()
    if not s:
        abort(404)
    if request.method == "POST":
        data = _student_form()
        try:
            db.execute("UPDATE students SET roll_no=?,name=?,email=?,phone=?,dept=?,year=? "
                       "WHERE id=?", data + (sid,))
            db.commit()
            flash("Student updated", "ok")
            return redirect(url_for("student_detail", sid=sid))
        except sqlite3.IntegrityError:
            flash("That roll number already exists", "error")
    return render_template("student_form.html", s=s)


@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required
def student_delete(sid):
    db = get_db()
    db.execute("DELETE FROM students WHERE id=?", (sid,))
    db.commit()
    flash("Student deleted", "ok")
    return redirect(url_for("students"))


# ---------- courses ----------
@app.route("/courses", methods=["GET", "POST"])
@login_required
def courses():
    db = get_db()
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        title = request.form.get("title", "").strip()
        credits = int(request.form.get("credits") or 3)
        if not code or not title:
            flash("Course code and title are required", "error")
        else:
            try:
                db.execute("INSERT INTO courses(code,title,credits) VALUES (?,?,?)",
                           (code, title, credits))
                db.commit()
                flash("Course added", "ok")
            except sqlite3.IntegrityError:
                flash("That course code already exists", "error")
        return redirect(url_for("courses"))
    rows = db.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM enrollments WHERE course_id=c.id) n "
        "FROM courses c ORDER BY code").fetchall()
    return render_template("courses.html", courses=rows)


@app.route("/courses/<int:cid>/delete", methods=["POST"])
@login_required
def course_delete(cid):
    db = get_db()
    db.execute("DELETE FROM courses WHERE id=?", (cid,))
    db.commit()
    flash("Course deleted", "ok")
    return redirect(url_for("courses"))


# ---------- enrollments ----------
@app.route("/students/<int:sid>/enroll", methods=["POST"])
@login_required
def enroll(sid):
    cid = request.form.get("course_id", type=int)
    if cid:
        db = get_db()
        try:
            db.execute("INSERT INTO enrollments(student_id,course_id) VALUES (?,?)",
                       (sid, cid))
            db.commit()
            flash("Enrolled", "ok")
        except sqlite3.IntegrityError:
            flash("Could not enroll", "error")
    return redirect(url_for("student_detail", sid=sid))


@app.route("/enrollments/<int:eid>/grade", methods=["POST"])
@login_required
def set_grade(eid):
    db = get_db()
    row = db.execute("SELECT student_id FROM enrollments WHERE id=?", (eid,)).fetchone()
    if not row:
        abort(404)
    db.execute("UPDATE enrollments SET grade=? WHERE id=?",
               (request.form.get("grade", "").strip()[:3], eid))
    db.commit()
    flash("Grade saved", "ok")
    return redirect(url_for("student_detail", sid=row["student_id"]))


@app.route("/enrollments/<int:eid>/delete", methods=["POST"])
@login_required
def unenroll(eid):
    db = get_db()
    row = db.execute("SELECT student_id FROM enrollments WHERE id=?", (eid,)).fetchone()
    if not row:
        abort(404)
    db.execute("DELETE FROM enrollments WHERE id=?", (eid,))
    db.commit()
    flash("Removed from course", "ok")
    return redirect(url_for("student_detail", sid=row["student_id"]))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
