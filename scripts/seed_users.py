from getpass import getpass

from app.core.security import hash_password
from app.db.models import Department, User
from app.db.session import get_engine
from sqlalchemy import select
from sqlalchemy.orm import Session

DEMO_USERS = [
    ("Operations", "operations@demo.local", "staff"),
    ("Finance", "finance@demo.local", "staff"),
    ("Management", "manager@demo.local", "manager"),
    ("IT", "admin@demo.local", "admin"),
]


def main():
    password = getpass("Enter a demo password (minimum 12 characters): ")

    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")

    with Session(get_engine()) as db:
        for department_name, email, role in DEMO_USERS:
            department = db.scalar(
                select(Department).where(
                    Department.name == department_name
                )
            )

            if department is None:
                department = Department(name=department_name)
                db.add(department)
                db.flush()

            existing_user = db.scalar(
                select(User).where(User.email == email)
            )

            if existing_user is None:
                user = User(
                    department_id=department.id,
                    email=email,
                    role=role,
                    password_hash=hash_password(password),
                )
                db.add(user)

        db.commit()

    print("Demo users created successfully.")


if __name__ == "__main__":
    main()