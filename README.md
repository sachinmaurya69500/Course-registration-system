# Course Registration System

Professional Flask-based course registration platform with role-based authentication, MongoDB Atlas integration, and Bootstrap 5 UI.

## Features

- Multi-role authentication with Flask-Login (Admin/Registrar and Student)
- Role-based access control for route protection
- Password hashing via Werkzeug security utilities
- Flash messaging for actions and enrollment outcomes
- Admin course CRUD (Create, Update, Delete)
- Enrollment management with capacity-aware logic
- Student schedule page with unenroll action
- Admin analytics dashboard using MongoDB aggregation:
	- Total courses
	- Total students
	- Most popular course
- Student portal table with DataTables and filters
- Full-capacity visual cue (`Full` badge)
- Dark/Light mode toggle using JavaScript + localStorage

## Project Folder Structure

```text
Course-registration-system/
├── app.py
├── models.py
├── requirements.txt
├── .env.template
├── README.md
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── theme.js
└── templates/
		├── base.html
		├── login.html
		├── register.html
		├── admin_dashboard.html
		├── student_portal.html
		├── course_form.html
		├── my_schedule.html
		└── course_students.html
```

## Course Document Fields

- `course_name`
- `course_code`
- `instructor`
- `department`
- `credits`
- `capacity`
- `enrolled_count`
- `enrolled_students` (array of student `ObjectId` values)

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy environment template and configure values:

```bash
cp .env.template .env
```

4. Add your MongoDB Atlas connection string in `.env`.
5. Run the app:

```bash
python app.py
```

6. Open `http://localhost:5000`.

## Authentication Notes

- Register as a Student by default.
- To register as Admin (Registrar), provide `ADMIN_REGISTRATION_CODE` value in the registration form.