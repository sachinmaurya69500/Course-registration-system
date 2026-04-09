import os
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from pymongo import MongoClient
from werkzeug.security import check_password_hash, generate_password_hash

from models import Course, User


load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-production")

mongo_uri = os.getenv("MONGO_URI")
db_name = os.getenv("MONGO_DB_NAME", "course_registration")
admin_registration_code = os.getenv("ADMIN_REGISTRATION_CODE", "")

if not mongo_uri:
    raise RuntimeError("MONGO_URI is not set. Add it to your .env file.")

mongo_client = MongoClient(mongo_uri)
db = mongo_client[db_name]

User.create_indexes(db)
Course.create_indexes(db)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "warning"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.find_by_id(db, user_id)


def role_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in allowed_roles:
                flash("You are not authorized to access that page.", "danger")
                return redirect(url_for("index"))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def parse_positive_int(value: str, default: int = 0) -> int:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else default
    except (TypeError, ValueError):
        return default


@app.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("student_portal"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        submitted_admin_code = request.form.get("admin_code", "").strip()

        if not username or not email or not password:
            flash("All required fields must be filled.", "danger")
            return render_template("register.html")

        role = "student"
        if admin_registration_code and submitted_admin_code == admin_registration_code:
            role = "admin"

        password_hash = generate_password_hash(password)
        _, error = User.create_user(db, username, email, password_hash, role)

        if error:
            flash(error, "danger")
            return render_template("register.html")

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.find_by_username(db, username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(url_for("index"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/admin/dashboard")
@login_required
@role_required("admin")
def admin_dashboard():
    courses = Course.list_courses(db)
    total_courses = db.courses.count_documents({})
    total_students = User.count_students(db)
    popular_course = Course.most_popular_course(db)
    return render_template(
        "admin_dashboard.html",
        courses=courses,
        total_courses=total_courses,
        total_students=total_students,
        popular_course=popular_course,
    )


@app.route("/admin/courses/new", methods=["GET", "POST"])
@login_required
@role_required("admin")
def create_course():
    if request.method == "POST":
        payload = {
            "course_name": request.form.get("course_name", "").strip(),
            "course_code": request.form.get("course_code", "").strip().upper(),
            "instructor": request.form.get("instructor", "").strip(),
            "department": request.form.get("department", "").strip().upper(),
            "credits": request.form.get("credits", "0").strip(),
            "capacity": request.form.get("capacity", "0").strip(),
        }

        if not all([payload["course_name"], payload["course_code"], payload["instructor"], payload["department"]]):
            flash("Please complete all course fields.", "danger")
            return render_template("course_form.html", mode="create", course=payload)

        try:
            _, error = Course.create_course(db, payload)
            if error:
                flash(error, "danger")
                return render_template("course_form.html", mode="create", course=payload)
            flash("Course created successfully.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError:
            flash("Credits and capacity must be valid numbers.", "danger")
            return render_template("course_form.html", mode="create", course=payload)

    return render_template("course_form.html", mode="create", course={})


@app.route("/admin/courses/<course_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_course(course_id):
    course = Course.get_by_id(db, course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        payload = {
            "course_name": request.form.get("course_name", "").strip(),
            "course_code": request.form.get("course_code", "").strip().upper(),
            "instructor": request.form.get("instructor", "").strip(),
            "department": request.form.get("department", "").strip().upper(),
            "credits": request.form.get("credits", "0").strip(),
            "capacity": request.form.get("capacity", "0").strip(),
        }

        if not all([payload["course_name"], payload["course_code"], payload["instructor"], payload["department"]]):
            flash("Please complete all course fields.", "danger")
            course.update(payload)
            return render_template("course_form.html", mode="edit", course=course)

        try:
            success, error = Course.update_course(db, course_id, payload)
            if not success:
                flash(error or "Unable to update course.", "danger")
                course.update(payload)
                return render_template("course_form.html", mode="edit", course=course)

            flash("Course updated successfully.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError:
            flash("Credits and capacity must be valid numbers.", "danger")
            course.update(payload)
            return render_template("course_form.html", mode="edit", course=course)

    return render_template("course_form.html", mode="edit", course=course)


@app.route("/admin/courses/<course_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_course(course_id):
    deleted = Course.delete_course(db, course_id)
    if deleted:
        flash("Course deleted.", "info")
    else:
        flash("Course not found.", "danger")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/courses/<course_id>/students")
@login_required
@role_required("admin")
def enrolled_students(course_id):
    course = Course.get_by_id(db, course_id)
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    students = Course.list_enrolled_students(db, course_id)
    return render_template("course_students.html", course=course, students=students)


@app.route("/student/portal")
@login_required
@role_required("student")
def student_portal():
    department = request.args.get("department", "").strip()
    credits_raw = request.args.get("credits", "").strip()
    credits = parse_positive_int(credits_raw, default=0) if credits_raw else None

    courses = Course.list_courses(db, department=department if department else None, credits=credits)
    schedule = Course.student_schedule(db, current_user.id)
    enrolled_course_ids = {c["id"] for c in schedule}

    departments = db.courses.distinct("department")
    credits_options = sorted(db.courses.distinct("credits"))

    return render_template(
        "student_portal.html",
        courses=courses,
        enrolled_course_ids=enrolled_course_ids,
        selected_department=department,
        selected_credits=credits_raw,
        departments=departments,
        credits_options=credits_options,
    )


@app.route("/student/courses/<course_id>/enroll", methods=["POST"])
@login_required
@role_required("student")
def enroll(course_id):
    status = Course.enroll_student(db, course_id, current_user.id)

    if status == "enrolled":
        flash("Enrolled Successfully!", "success")
    elif status == "already":
        flash("You are already enrolled in this course.", "warning")
    elif status == "full":
        flash("Course is Full!", "danger")
    else:
        flash("Unable to enroll in this course.", "danger")

    return redirect(url_for("student_portal"))


@app.route("/student/schedule")
@login_required
@role_required("student")
def my_schedule():
    courses = Course.student_schedule(db, current_user.id)
    return render_template("my_schedule.html", courses=courses)


@app.route("/student/courses/<course_id>/unenroll", methods=["POST"])
@login_required
@role_required("student")
def unenroll(course_id):
    status = Course.unenroll_student(db, course_id, current_user.id)
    if status == "removed":
        flash("You have been unenrolled from the course.", "info")
    else:
        flash("You are not enrolled in that course.", "warning")
    return redirect(url_for("my_schedule"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
import os
from datetime import datetime
from functools import wraps

from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash

from models import Course, User

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")

mongo_uri = os.getenv("MONGO_URI")
mongo_db_name = os.getenv("MONGO_DB", "course_registration")

if not mongo_uri:
    raise RuntimeError("MONGO_URI is not configured. Copy .env.template to .env and set it.")

client = MongoClient(mongo_uri)
db = client[mongo_db_name]
users_col = db["users"]
courses_col = db["courses"]

users_col.create_index("email", unique=True)
users_col.create_index("username", unique=True)
courses_col.create_index("code", unique=True)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "warning"
login_manager.init_app(app)


class LoginUser(UserMixin):
    def __init__(self, user_doc):
        self.id = str(user_doc["_id"])
        self.username = user_doc["username"]
        self.email = user_doc["email"]
        self.role = user_doc["role"]


@login_manager.user_loader
def load_user(user_id):
    user_doc = users_col.find_one({"_id": ObjectId(user_id)})
    return LoginUser(user_doc) if user_doc else None


def role_required(role):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role != role:
                flash("You do not have permission to access this page.", "danger")
                return redirect(url_for("dashboard"))
            return func(*args, **kwargs)

        return wrapped

    return decorator


def parse_course_form(form):
    payload = {
        "name": form.get("name", ""),
        "code": form.get("code", ""),
        "instructor": form.get("instructor", ""),
        "department": form.get("department", ""),
        "credits": form.get("credits", "0"),
        "capacity": form.get("capacity", "0"),
    }
    if not all(payload.values()):
        raise ValueError("All course fields are required.")

    payload["credits"] = int(payload["credits"])
    payload["capacity"] = int(payload["capacity"])

    if payload["credits"] < 1:
        raise ValueError("Credits must be at least 1.")
    if payload["capacity"] < 1:
        raise ValueError("Capacity must be at least 1.")

    return payload


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html")

        role = User.ROLE_STUDENT
        if users_col.count_documents({}) == 0:
            role = User.ROLE_ADMIN

        try:
            users_col.insert_one(User.build_document(username, email, password, role=role))
            flash("Registration successful. Please log in.", "success")
            if role == User.ROLE_ADMIN:
                flash("First account created as Admin (Registrar).", "info")
            return redirect(url_for("login"))
        except DuplicateKeyError:
            flash("Username or email already exists.", "danger")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user_doc = users_col.find_one({"email": email})
        if user_doc and check_password_hash(user_doc["password_hash"], password):
            login_user(LoginUser(user_doc))
            flash(f"Welcome back, {user_doc['username']}!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == User.ROLE_ADMIN:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("student_portal"))


@app.route("/admin/dashboard")
@login_required
@role_required(User.ROLE_ADMIN)
def admin_dashboard():
    total_courses = courses_col.count_documents({})
    total_students = users_col.count_documents({"role": User.ROLE_STUDENT})

    popular_result = list(
        courses_col.aggregate(
            [
                {"$sort": {"enrolled_count": -1, "name": 1}},
                {"$limit": 1},
            ]
        )
    )
    most_popular_course = popular_result[0] if popular_result else None

    courses = []
    for course in courses_col.find().sort("department", 1):
        course["id"] = str(course["_id"])
        enrolled_ids = [ObjectId(uid) for uid in course.get("enrolled_students", []) if ObjectId.is_valid(uid)]
        students = []
        if enrolled_ids:
            students = list(
                users_col.find(
                    {"_id": {"$in": enrolled_ids}},
                    {"username": 1, "email": 1},
                )
            )
        course["students"] = students
        courses.append(course)

    return render_template(
        "admin_dashboard.html",
        total_courses=total_courses,
        total_students=total_students,
        most_popular_course=most_popular_course,
        courses=courses,
    )


@app.route("/admin/courses/new", methods=["GET", "POST"])
@login_required
@role_required(User.ROLE_ADMIN)
def create_course():
    if request.method == "POST":
        try:
            payload = parse_course_form(request.form)
            course_doc = Course.build_document(payload)
            courses_col.insert_one(course_doc)
            flash("Course created successfully.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except DuplicateKeyError:
            flash("Course code already exists.", "danger")

    return render_template("course_form.html", mode="create", course={})


@app.route("/admin/courses/<course_id>/edit", methods=["GET", "POST"])
@login_required
@role_required(User.ROLE_ADMIN)
def edit_course(course_id):
    course = courses_col.find_one({"_id": ObjectId(course_id)})
    if not course:
        flash("Course not found.", "warning")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        try:
            payload = parse_course_form(request.form)
            if payload["capacity"] < course.get("enrolled_count", 0):
                flash("Capacity cannot be less than enrolled count.", "danger")
                return render_template("course_form.html", mode="edit", course=course)

            update_doc = Course.update_document(payload)
            courses_col.update_one({"_id": ObjectId(course_id)}, {"$set": update_doc})
            flash("Course updated successfully.", "success")
            return redirect(url_for("admin_dashboard"))
        except ValueError as exc:
            flash(str(exc), "danger")
        except DuplicateKeyError:
            flash("Course code already exists.", "danger")

    course["id"] = str(course["_id"])
    return render_template("course_form.html", mode="edit", course=course)


@app.route("/admin/courses/<course_id>/delete", methods=["POST"])
@login_required
@role_required(User.ROLE_ADMIN)
def delete_course(course_id):
    result = courses_col.delete_one({"_id": ObjectId(course_id)})
    if result.deleted_count == 0:
        flash("Course not found.", "warning")
    else:
        flash("Course deleted successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/student/portal")
@login_required
@role_required(User.ROLE_STUDENT)
def student_portal():
    courses = []
    for course in courses_col.find().sort("department", 1):
        course["id"] = str(course["_id"])
        enrolled_students = course.get("enrolled_students", [])
        course["is_enrolled"] = current_user.id in enrolled_students
        course["is_full"] = course.get("enrolled_count", 0) >= course.get("capacity", 0)
        courses.append(course)

    departments = sorted(courses_col.distinct("department"))
    return render_template("student_portal.html", courses=courses, departments=departments)


@app.route("/student/enroll/<course_id>", methods=["POST"])
@login_required
@role_required(User.ROLE_STUDENT)
def enroll(course_id):
    now = datetime.utcnow()
    updated_course = courses_col.find_one_and_update(
        {
            "_id": ObjectId(course_id),
            "enrolled_count": {"$lt": "$capacity"},
            "enrolled_students": {"$ne": current_user.id},
        },
        {
            "$inc": {"enrolled_count": 1},
            "$addToSet": {"enrolled_students": current_user.id},
            "$set": {"updated_at": now},
        },
        return_document=True,
    )

    if updated_course:
        flash("Enrolled Successfully!", "success")
        return redirect(url_for("student_portal"))

    course = courses_col.find_one({"_id": ObjectId(course_id)})
    if not course:
        flash("Course not found.", "warning")
    elif current_user.id in course.get("enrolled_students", []):
        flash("You are already enrolled in this course.", "info")
    elif course.get("enrolled_count", 0) >= course.get("capacity", 0):
        flash("Course is Full!", "warning")
    else:
        flash("Could not enroll in this course.", "danger")

    return redirect(url_for("student_portal"))


@app.route("/student/schedule")
@login_required
@role_required(User.ROLE_STUDENT)
def my_schedule():
    courses = list(
        courses_col.find({"enrolled_students": current_user.id}).sort("department", 1)
    )
    for course in courses:
        course["id"] = str(course["_id"])
    return render_template("my_schedule.html", courses=courses)


@app.route("/student/unenroll/<course_id>", methods=["POST"])
@login_required
@role_required(User.ROLE_STUDENT)
def unenroll(course_id):
    result = courses_col.update_one(
        {
            "_id": ObjectId(course_id),
            "enrolled_students": current_user.id,
            "enrolled_count": {"$gt": 0},
        },
        {
            "$pull": {"enrolled_students": current_user.id},
            "$inc": {"enrolled_count": -1},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )

    if result.modified_count > 0:
        flash("Unenrolled successfully.", "success")
    else:
        flash("You are not enrolled in this course.", "warning")

    return redirect(url_for("my_schedule"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
