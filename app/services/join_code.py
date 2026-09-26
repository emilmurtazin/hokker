"""
Постоянный числовой код тренера для самостоятельного присоединения родителей
(см. POST /coaches/join). 6 цифр (100000–999999) — 900 000 вариантов, легко
продиктовать и ввести на телефоне; хватает с большим запасом на масштаб школы.
"""

import secrets

from sqlalchemy.orm import Session

from app.models.coach import Coach

CODE_LENGTH = 6
_MIN, _MAX = 10 ** (CODE_LENGTH - 1), 10**CODE_LENGTH - 1  # 100000, 999999
_MAX_ATTEMPTS = 30


def generate_unique_join_code(db: Session) -> str:
    for _ in range(_MAX_ATTEMPTS):
        code = str(secrets.randbelow(_MAX - _MIN + 1) + _MIN)
        if db.query(Coach.id).filter(Coach.join_code == code).first() is None:
            return code
    # При 900 000 вариантов и разумном числе тренеров это практически невозможно;
    # явная ошибка лучше, чем тихая гонка за уникальность.
    raise RuntimeError("Не удалось подобрать свободный код тренера, попробуйте ещё раз")
