"""
Создание платформенного администратора (роль admin) — единственный способ
получить эту роль, публичная регистрация её не допускает (см.
app/schemas/auth.py: RegisterIn.role).

Запуск (внутри контейнера с доступом к DATABASE_URL, например через
консоль Timeweb App Platform, если она есть, либо локально, временно
включив публичный IP у БД):

    python scripts/create_admin.py +79991234567 "Имя Администратора"

После этого администратор входит в приложение обычным способом —
через /auth/request-code и /auth/verify-code по этому номеру телефона
(SMS-код), но /auth/register вызывать НЕ нужно — пользователь уже создан.
"""

import sys

sys.path.insert(0, ".")

from app.core.database import SessionLocal
from app.models.enums import UserRole
from app.models.user import User


def main():
    if len(sys.argv) < 3:
        print("Использование: python scripts/create_admin.py <телефон> <имя>")
        sys.exit(1)

    phone, name = sys.argv[1], sys.argv[2]

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.phone == phone).first()
        if existing:
            print(f"Пользователь с телефоном {phone} уже существует (роль: {existing.role.value}).")
            if existing.role != UserRole.admin:
                existing.role = UserRole.admin
                db.commit()
                print("Роль обновлена на admin.")
            sys.exit(0)

        admin = User(role=UserRole.admin, name=name, phone=phone)
        db.add(admin)
        db.commit()
        print(f"Создан администратор: id={admin.id}, phone={phone}, name={name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
