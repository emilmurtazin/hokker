"""
Логика бота: меню по ролям и ответы на команды. HTTP-часть (вебхук, привязка
аккаунта) живёт в app/api/telegram.py, отправка — в app/services/telegram.py.

Как устроено меню:
  - Кнопка «Меню» рядом с полем ввода показывает список команд (BOT_COMMANDS).
    Список один на все роли; что именно ответит команда, зависит от роли.
  - Команда /menu (и /start для привязанного аккаунта) показывает постоянную
    клавиатуру под полем ввода. Её кнопки открывают нужный раздел приложения
    одним нажатием (Web App), поэтому у каждой роли свой набор.
  - /schedule и /requests сразу показывают данные в чате + кнопку «Открыть».

Пути разделов соответствуют маршрутам фронтенда (src/App.jsx).
"""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.coach_player import CoachPlayer
from app.models.enums import BookingStatus, CoachPlayerStatus, SlotRequestStatus, SlotStatus
from app.models.ice_slot import IceSlot
from app.models.player import Player
from app.models.slot_request import SlotRequest
from app.models.training_session import TrainingSession
from app.models.user import User
from app.services.formatting import format_dt, session_title
from app.services.telegram import (
    esc,
    open_app_button,
    open_app_markup,
    reply_keyboard,
)

# --- Клавиатуры по ролям: [(подпись, путь в приложении), ...] по строкам ---
MENU_ROWS: dict[str, list[list[tuple[str, str]]]] = {
    "parent": [
        [("📅 Расписание", "/schedule"), ("🔎 Тренировки", "/")],
        [("🎬 Упражнения", "/exercises"), ("👤 Профиль", "/profile")],
    ],
    "coach": [
        [("📅 Тренировки", "/"), ("👥 Ученики", "/players")],
        [("🧊 Лёд", "/ice"), ("🎬 Упражнения", "/exercises")],
        [("👤 Профиль", "/profile")],
    ],
    "arena_admin": [
        [("🧊 Слоты", "/"), ("📥 Заявки", "/requests")],
        [("👤 Профиль", "/profile")],
    ],
    "admin": [
        [("🎬 Упражнения", "/exercises"), ("👤 Профиль", "/profile")],
    ],
}

# У арены нет раздела упражнений (см. ArenaRoutes во фронтенде).
_NO_EXERCISES = {"arena_admin"}

_ICE_TYPE = {"full": "полный лёд", "half": "половина", "third": "треть"}
_SLOT_STATUS = {"available": "свободен", "pending": "есть заявка", "booked": "занят"}
_BOOKING_STATUS = {
    BookingStatus.confirmed: "✅",
    BookingStatus.pending: "⏳ ждёт тренера",
    BookingStatus.waiting: "🕓 лист ожидания",
    BookingStatus.invited: "🎟 подтвердите место!",
}

MAX_LINES = 8  # чтобы ответ не превращался в простыню


def role_of(user: User) -> str:
    return user.role.value


def main_markup(role: str) -> dict | None:
    """Постоянная клавиатура под полем ввода; без HTTPS — inline-кнопки-ссылки."""
    rows = MENU_ROWS.get(role) or MENU_ROWS["parent"]
    keyboard = reply_keyboard(rows)
    if keyboard is not None:
        return keyboard
    return {
        "inline_keyboard": [[open_app_button(label, path) for label, path in row] for row in rows]
    }


def _more(total: int, shown: int) -> str:
    return f"\n… и ещё {total - shown}" if total > shown else ""


# ---------------------------------------------------------------- команды ---


def cmd_menu(db: Session, user: User) -> tuple[str, dict | None]:
    return (
        f"Привет, {esc(user.name)}! 👋\nВыберите раздел кнопками ниже — они откроют приложение.",
        main_markup(role_of(user)),
    )


def cmd_schedule(db: Session, user: User) -> tuple[str, dict | None]:
    role = role_of(user)
    now = datetime.now(timezone.utc)

    if role == "parent":
        rows = (
            db.query(Booking, TrainingSession, Player)
            .join(TrainingSession, TrainingSession.id == Booking.session_id)
            .join(Player, Player.id == Booking.player_id)
            .filter(
                Player.parent_id == user.id,
                Booking.status.in_(list(_BOOKING_STATUS)),
                TrainingSession.datetime_ >= now,
            )
            .order_by(TrainingSession.datetime_.asc())
            .all()
        )
        if not rows:
            text = "📅 Ближайших записей нет.\nНайдите тренера и запишите ребёнка на тренировку."
        else:
            lines = [
                f"• {esc(session_title(s))} — {esc(p.name)} {_BOOKING_STATUS[b.status]}"
                for b, s, p in rows[:MAX_LINES]
            ]
            text = "📅 <b>Ближайшие тренировки</b>\n" + "\n".join(lines) + _more(len(rows), MAX_LINES)
        return text, open_app_markup("Открыть расписание", "/schedule")

    if role == "coach":
        sessions = (
            db.query(TrainingSession)
            .filter(TrainingSession.coach_id == user.id, TrainingSession.datetime_ >= now)
            .order_by(TrainingSession.datetime_.asc())
            .limit(MAX_LINES)
            .all()
        )
        if not sessions:
            text = "📅 Ближайших тренировок нет.\nСоздайте тренировку в приложении."
        else:
            counts = dict(
                db.query(Booking.session_id, func.count(Booking.id))
                .filter(
                    Booking.session_id.in_([s.id for s in sessions]),
                    Booking.status == BookingStatus.confirmed,
                )
                .group_by(Booking.session_id)
                .all()
            )
            lines = [
                f"• {esc(session_title(s))} — записано {counts.get(s.id, 0)}/{s.max_players}"
                for s in sessions
            ]
            text = "📅 <b>Ближайшие тренировки</b>\n" + "\n".join(lines)
        return text, open_app_markup("Открыть тренировки", "/")

    if role == "arena_admin":
        slots = (
            db.query(IceSlot)
            .filter(
                IceSlot.arena_id == user.id,
                IceSlot.date >= now.date(),
                IceSlot.status.in_([SlotStatus.available, SlotStatus.pending, SlotStatus.booked]),
            )
            .order_by(IceSlot.date.asc(), IceSlot.time_start.asc())
            .limit(MAX_LINES)
            .all()
        )
        if not slots:
            text = "🧊 Ближайших слотов нет.\nОпубликуйте свободное время льда в приложении."
        else:
            lines = [
                f"• {sl.date.strftime('%d.%m')} {sl.time_start.strftime('%H:%M')}–"
                f"{sl.time_end.strftime('%H:%M')}, {_ICE_TYPE.get(sl.ice_type.value, '')} — "
                f"{_SLOT_STATUS.get(sl.status.value, '')}"
                for sl in slots
            ]
            text = "🧊 <b>Ближайшие слоты</b>\n" + "\n".join(lines)
        return text, open_app_markup("Открыть слоты", "/")

    return "Для вашей роли этот раздел недоступен.", open_app_markup("Открыть приложение", "/")


def cmd_requests(db: Session, user: User) -> tuple[str, dict | None]:
    role = role_of(user)

    if role == "coach":
        rows = (
            db.query(Booking, TrainingSession, Player)
            .join(TrainingSession, TrainingSession.id == Booking.session_id)
            .join(Player, Player.id == Booking.player_id)
            .filter(TrainingSession.coach_id == user.id, Booking.status == BookingStatus.pending)
            .order_by(Booking.created_at.asc())
            .all()
        )
        if not rows:
            return "📥 Новых заявок на подтверждение нет. 👍", open_app_markup("Открыть тренировки", "/")
        lines = [f"• {esc(p.name)} — {esc(session_title(s))}" for b, s, p in rows[:MAX_LINES]]
        text = f"📥 <b>Заявки ждут подтверждения: {len(rows)}</b>\n" + "\n".join(lines)
        return text + _more(len(rows), MAX_LINES), open_app_markup("Открыть заявки", "/")

    if role == "arena_admin":
        rows = (
            db.query(SlotRequest, IceSlot, User)
            .join(IceSlot, IceSlot.id == SlotRequest.slot_id)
            .join(User, User.id == SlotRequest.coach_id)
            .filter(IceSlot.arena_id == user.id, SlotRequest.status == SlotRequestStatus.pending)
            .order_by(SlotRequest.created_at.asc())
            .all()
        )
        if not rows:
            return "📥 Новых заявок на лёд нет. 👍", open_app_markup("Открыть заявки", "/requests")
        lines = [
            f"• {esc(coach.name)} — {sl.date.strftime('%d.%m')} "
            f"{sl.time_start.strftime('%H:%M')}–{sl.time_end.strftime('%H:%M')}"
            for _, sl, coach in rows[:MAX_LINES]
        ]
        text = f"📥 <b>Заявки на лёд: {len(rows)}</b>\n" + "\n".join(lines)
        return text + _more(len(rows), MAX_LINES), open_app_markup("Открыть заявки", "/requests")

    if role == "parent":
        invited = (
            db.query(Booking, TrainingSession, Player)
            .join(TrainingSession, TrainingSession.id == Booking.session_id)
            .join(Player, Player.id == Booking.player_id)
            .filter(Player.parent_id == user.id, Booking.status == BookingStatus.invited)
            .order_by(TrainingSession.datetime_.asc())
            .all()
        )
        invites = (
            db.query(CoachPlayer, User, Player)
            .join(Player, Player.id == CoachPlayer.player_id)
            .join(User, User.id == CoachPlayer.coach_id)
            .filter(Player.parent_id == user.id, CoachPlayer.status == CoachPlayerStatus.pending)
            .all()
        )
        if not invited and not invites:
            return "📥 Ничего не требует вашего решения. 👍", open_app_markup("Открыть расписание", "/schedule")

        parts, buttons = [], []
        if invited:
            parts.append("🎟 <b>Освободилось место — подтвердите:</b>")
            parts += [f"• {esc(p.name)} — {esc(session_title(s))}" for b, s, p in invited[:MAX_LINES]]
            buttons.append(open_app_button("Подтвердить место", "/schedule"))
        if invites:
            parts.append("🤝 <b>Приглашения от тренеров:</b>")
            parts += [f"• {esc(coach.name)} — {esc(p.name)}" for cp, coach, p in invites[:MAX_LINES]]
            buttons.append(open_app_button("Приглашения", "/profile"))
        return "\n".join(parts), {"inline_keyboard": [[b] for b in buttons]}

    return "Для вашей роли этот раздел недоступен.", open_app_markup("Открыть приложение", "/")


def cmd_exercises(db: Session, user: User) -> tuple[str, dict | None]:
    if role_of(user) in _NO_EXERCISES:
        return "Каталог упражнений доступен тренерам и родителям.", open_app_markup("Открыть приложение", "/")
    return (
        "🎬 <b>Каталог упражнений</b>\nВидео и карточки: катание, броски, ОФП, вратарская техника.",
        open_app_markup("Открыть каталог", "/exercises"),
    )


def cmd_profile(db: Session, user: User) -> tuple[str, dict | None]:
    return (
        f"👤 <b>{esc(user.name)}</b>\nИмя, город, дети и настройки — в профиле приложения.\n"
        "Уведомления приходят в этот чат. Отключить: /unlink",
        open_app_markup("Открыть профиль", "/profile"),
    )


def cmd_help(db: Session, user: User) -> tuple[str, dict | None]:
    lines = [
        "/menu — главное меню с кнопками",
        "/schedule — ближайшие тренировки" if role_of(user) != "arena_admin" else "/schedule — ближайшие слоты",
        "/requests — заявки и приглашения",
    ]
    if role_of(user) not in _NO_EXERCISES:
        lines.append("/exercises — каталог упражнений")
    lines += [
        "/profile — профиль",
        "/whoami — к какому аккаунту привязан этот чат",
        "/unlink — отключить уведомления",
    ]
    return "🏒 <b>Команды бота Хоккер</b>\n" + "\n".join(lines), open_app_markup("Открыть приложение", "/")


def cmd_whoami(db: Session, user: User) -> tuple[str, dict | None]:
    return (
        f"👤 Аккаунт: <b>{esc(user.name)}</b>\n"
        f"📞 Телефон: {esc(user.phone)}\n"
        f"🎭 Роль: {esc(role_of(user))}\n"
        f"🆔 User ID: {user.id}",
        None,
    )


# Команды, доступные только привязанному аккаунту.
COMMANDS = {
    "menu": cmd_menu,
    "schedule": cmd_schedule,
    "requests": cmd_requests,
    "exercises": cmd_exercises,
    "profile": cmd_profile,
    "help": cmd_help,
    "whoami": cmd_whoami,
}


def parse_command(text: str) -> tuple[str | None, str]:
    """'/schedule@hokker_bot' → ('schedule', ''); '/start abc' → ('start', 'abc'); 'привет' → (None, '')."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None, ""
    head, _, arg = text.partition(" ")
    command = head[1:].split("@", 1)[0].lower()
    return command, arg.strip()
