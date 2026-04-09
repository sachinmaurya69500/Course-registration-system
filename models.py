from dataclasses import dataclass
from typing import Optional

from bson import ObjectId
from flask_login import UserMixin
from pymongo.errors import DuplicateKeyError


@dataclass
class User(UserMixin):
    id: str
    username: str
    email: str
    password_hash: str
    role: str = "student"

    def get_id(self) -> str:
        return self.id

    @staticmethod
    def from_doc(doc: dict) -> "User":
        return User(
            id=str(doc["_id"]),
            username=doc["username"],
            email=doc["email"],
            password_hash=doc["password_hash"],
            role=doc.get("role", "student"),
        )

    @staticmethod
    def create_indexes(db):
        db.users.create_index("username", unique=True)
        db.users.create_index("email", unique=True)
        db.users.create_index("role")

    @staticmethod
    def find_by_id(db, user_id: str) -> Optional["User"]:
        if not ObjectId.is_valid(user_id):
            return None
        doc = db.users.find_one({"_id": ObjectId(user_id)})
        return User.from_doc(doc) if doc else None

    @staticmethod
    def find_by_username(db, username: str) -> Optional["User"]:
        doc = db.users.find_one({"username": username})
        return User.from_doc(doc) if doc else None

    @staticmethod
    def find_by_email(db, email: str) -> Optional["User"]:
        doc = db.users.find_one({"email": email})
        return User.from_doc(doc) if doc else None

    @staticmethod
    def create_user(db, username: str, email: str, password_hash: str, role: str = "student"):
        try:
            result = db.users.insert_one(
                {
                    "username": username,
                    "email": email,
                    "password_hash": password_hash,
                    "role": role,
                }
            )
            return str(result.inserted_id), None
        except DuplicateKeyError:
            return None, "Username or email already exists."

    @staticmethod
    def count_students(db) -> int:
        return db.users.count_documents({"role": "student"})

    @staticmethod
    def list_by_ids(db, user_ids: list[str]) -> list[dict]:
        valid_ids = [ObjectId(uid) for uid in user_ids if ObjectId.is_valid(uid)]
        if not valid_ids:
            return []
        docs = db.users.find(
            {"_id": {"$in": valid_ids}},
            {"username": 1, "email": 1, "role": 1},
        )
        return [
            {
                "id": str(doc["_id"]),
                "username": doc.get("username", "N/A"),
                "email": doc.get("email", "N/A"),
                "role": doc.get("role", "student"),
            }
            for doc in docs
        ]


class Course:
    @staticmethod
    def create_indexes(db):
        db.courses.create_index("course_code", unique=True)
        db.courses.create_index("department")
        db.courses.create_index("credits")
        db.courses.create_index("enrolled_count")

    @staticmethod
    def _normalize(doc: dict) -> dict:
        if not doc:
            return {}
        return {
            "id": str(doc["_id"]),
            "course_name": doc["course_name"],
            "course_code": doc["course_code"],
            "instructor": doc["instructor"],
            "department": doc["department"],
            "credits": doc["credits"],
            "capacity": doc["capacity"],
            "enrolled_count": doc.get("enrolled_count", 0),
            "enrolled_students": [str(uid) for uid in doc.get("enrolled_students", [])],
        }

    @staticmethod
    def create_course(db, payload: dict):
        payload["credits"] = int(payload["credits"])
        payload["capacity"] = int(payload["capacity"])
        payload["enrolled_count"] = 0
        payload["enrolled_students"] = []
        try:
            result = db.courses.insert_one(payload)
            return str(result.inserted_id), None
        except DuplicateKeyError:
            return None, "Course code already exists."

    @staticmethod
    def update_course(db, course_id: str, payload: dict):
        if not ObjectId.is_valid(course_id):
            return False, "Invalid course ID."

        course = db.courses.find_one({"_id": ObjectId(course_id)})
        if not course:
            return False, "Course not found."

        credits = int(payload["credits"])
        capacity = int(payload["capacity"])
        if capacity < course.get("enrolled_count", 0):
            return False, "Capacity cannot be less than currently enrolled students."

        update_doc = {
            "course_name": payload["course_name"],
            "course_code": payload["course_code"],
            "instructor": payload["instructor"],
            "department": payload["department"],
            "credits": credits,
            "capacity": capacity,
        }

        try:
            db.courses.update_one({"_id": ObjectId(course_id)}, {"$set": update_doc})
            return True, None
        except DuplicateKeyError:
            return False, "Course code already exists."

    @staticmethod
    def delete_course(db, course_id: str) -> bool:
        if not ObjectId.is_valid(course_id):
            return False
        result = db.courses.delete_one({"_id": ObjectId(course_id)})
        return result.deleted_count == 1

    @staticmethod
    def get_by_id(db, course_id: str) -> Optional[dict]:
        if not ObjectId.is_valid(course_id):
            return None
        doc = db.courses.find_one({"_id": ObjectId(course_id)})
        return Course._normalize(doc) if doc else None

    @staticmethod
    def list_courses(db, department: Optional[str] = None, credits: Optional[int] = None) -> list[dict]:
        query = {}
        if department:
            query["department"] = {"$regex": f"^{department}$", "$options": "i"}
        if credits is not None:
            query["credits"] = int(credits)

        docs = db.courses.find(query).sort([("department", 1), ("course_code", 1)])
        return [Course._normalize(doc) for doc in docs]

    @staticmethod
    def enroll_student(db, course_id: str, student_id: str) -> str:
        if not ObjectId.is_valid(course_id) or not ObjectId.is_valid(student_id):
            return "missing"

        course_obj = ObjectId(course_id)
        student_obj = ObjectId(student_id)

        result = db.courses.update_one(
            {
                "_id": course_obj,
                "enrolled_students": {"$ne": student_obj},
                "$expr": {"$lt": ["$enrolled_count", "$capacity"]},
            },
            {
                "$addToSet": {"enrolled_students": student_obj},
                "$inc": {"enrolled_count": 1},
            },
        )

        if result.modified_count == 1:
            return "enrolled"

        existing = db.courses.find_one({"_id": course_obj}, {"capacity": 1, "enrolled_count": 1, "enrolled_students": 1})
        if not existing:
            return "missing"
        if student_obj in existing.get("enrolled_students", []):
            return "already"
        if existing.get("enrolled_count", 0) >= existing.get("capacity", 0):
            return "full"
        return "missing"

    @staticmethod
    def unenroll_student(db, course_id: str, student_id: str) -> str:
        if not ObjectId.is_valid(course_id) or not ObjectId.is_valid(student_id):
            return "missing"

        result = db.courses.update_one(
            {
                "_id": ObjectId(course_id),
                "enrolled_students": ObjectId(student_id),
            },
            {
                "$pull": {"enrolled_students": ObjectId(student_id)},
                "$inc": {"enrolled_count": -1},
            },
        )

        return "removed" if result.modified_count == 1 else "not_enrolled"

    @staticmethod
    def student_schedule(db, student_id: str) -> list[dict]:
        if not ObjectId.is_valid(student_id):
            return []
        docs = db.courses.find({"enrolled_students": ObjectId(student_id)}).sort("course_code", 1)
        return [Course._normalize(doc) for doc in docs]

    @staticmethod
    def most_popular_course(db) -> Optional[dict]:
        pipeline = [
            {"$sort": {"enrolled_count": -1, "course_code": 1}},
            {"$limit": 1},
            {
                "$project": {
                    "_id": 0,
                    "course_name": 1,
                    "course_code": 1,
                    "enrolled_count": 1,
                }
            },
        ]
        result = list(db.courses.aggregate(pipeline))
        return result[0] if result else None

    @staticmethod
    def list_enrolled_students(db, course_id: str) -> list[dict]:
        course = Course.get_by_id(db, course_id)
        if not course:
            return []
        return User.list_by_ids(db, course.get("enrolled_students", []))
from datetime import datetime
from werkzeug.security import generate_password_hash


class User:
    ROLE_ADMIN = "admin"
    ROLE_STUDENT = "student"
    ALLOWED_ROLES = {ROLE_ADMIN, ROLE_STUDENT}

    @staticmethod
    def build_document(username, email, password, role=ROLE_STUDENT):
        normalized_role = role if role in User.ALLOWED_ROLES else User.ROLE_STUDENT
        return {
            "username": username.strip(),
            "email": email.strip().lower(),
            "password_hash": generate_password_hash(password),
            "role": normalized_role,
            "created_at": datetime.utcnow(),
        }


class Course:
    REQUIRED_FIELDS = {
        "name",
        "code",
        "instructor",
        "department",
        "credits",
        "capacity",
    }

    @staticmethod
    def build_document(payload):
        return {
            "name": payload["name"].strip(),
            "code": payload["code"].strip().upper(),
            "instructor": payload["instructor"].strip(),
            "department": payload["department"].strip().upper(),
            "credits": int(payload["credits"]),
            "capacity": int(payload["capacity"]),
            "enrolled_count": 0,
            "enrolled_students": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

    @staticmethod
    def update_document(payload):
        return {
            "name": payload["name"].strip(),
            "code": payload["code"].strip().upper(),
            "instructor": payload["instructor"].strip(),
            "department": payload["department"].strip().upper(),
            "credits": int(payload["credits"]),
            "capacity": int(payload["capacity"]),
            "updated_at": datetime.utcnow(),
        }
