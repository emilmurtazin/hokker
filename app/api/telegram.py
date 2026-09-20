import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.telegram_link_token import TelegramLinkToken
from app.models.user import User
from app.schemas.telegram import TelegramLinkOut
from app.services.telegram import REMOVE_KEYBOARD, esc, send_message
from app.services.telegram_bot import COMMANDS, main_markup, parse_command, role_of

router = APIRouter(tags=["telegram"])


@router.get("/telegram/link", response_model=TelegramLinkOut)
def get_link(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(
            status_code=503,
            detail="Telegram-бот ещё не настроен на сервере (TELEGRAM_BOT_USERNAME пуст)",
        )

    # Удаляем все прежние неиспользованные токены пользователя
    db.query(TelegramLinkToken).filter(
        TelegramLinkToken.user_id == user.id,
        TelegramLinkToken.used.is_(False),
    ).delete()

    import secrets
    link = TelegramLinkToken(user_id=user.id, token=secrets.token_urlsafe(32))
    db.add(link)
    db.commit()
    db.refresh(link)

    deep_link = f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={link.token}"
    return TelegramLinkOut(deep_link=deep_link)


@router.post("/internal/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """
    Telegram присылает сюда апдейты. Секрет проверяется, если задан
    TELEGRAM_WEBHOOK_SECRET. Токен привязки ищем в БД (короткий, одноразовый).

    Что обрабатываем (только личные чаты):
      /start <токен>  — привязка Telegram к аккаунту
      /start          — приветствие; для привязанного аккаунта — главное меню
      /menu /schedule /requests /exercises /profile /help /whoami — см. telegram_bot.py
      /unlink         — отвязать Telegram (уведомления прекращаются)
    """
    if settings.TELEGRAM_WEBHOOK_SECRET:
        received = (x_telegram_bot_api_secret_token or "").encode()
        expected = settings.TELEGRAM_WEBHOOK_SECRET.encode()
        if not hmac.compare_digest(received, expected):
            raise HTTPException(status_code=401, detail="Неверный секрет вебхука")

    update = await request.json()
    message = update.get("message")
    if not message:
        return {"ok": True}

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    # Бот работает только в личке: кнопки Web App и уведомления в группах не нужны.
    if chat_id is None or chat.get("type") != "private":
        return {"ok": True}

    def reply(reply_text: str, reply_markup: dict | None = None) -> dict:
        background.add_task(send_message, str(chat_id), reply_text, reply_markup)
        return {"ok": True}

    command, arg = parse_command(message.get("text") or "")
    user = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()

    # --- /start <токен> — привязка аккаунта ---
    if command == "start" and arg:
        return _link_account(db, str(chat_id), arg, reply)

    # --- отвязка ---
    if command == "unlink":
        if user is None:
            return reply("Этот Telegram и так не привязан ни к одному аккаунту.")
        user.telegram_chat_id = None
        db.commit()
        return reply(
            "🔕 Telegram отвязан — уведомления приходить не будут.\n"
            "Вернуть: приложение → Профиль → «Привязать Telegram».",
            REMOVE_KEYBOARD,
        )

    # --- Не привязан: всё, кроме /start, ведёт на инструкцию по привязке ---
    if user is None:
        return reply_not_linked(reply)

    # --- Привязан: /start — то же, что /menu; остальное — по таблице команд ---
    handler = COMMANDS["menu"] if command == "start" else COMMANDS.get(command or "")
    if handler is None:
        # неизвестная команда или обычный текст
        return reply("Не понял 🤔 Воспользуйтесь кнопками меню или командой /help.", main_markup(role_of(user)))

    text_out, markup = handler(db, user)
    return reply(text_out, markup)


def reply_not_linked(reply) -> dict:
    app_url = settings.APP_PUBLIC_URL or "https://24hokker.ru"
    text_out = (
        "👋 Привет! Я бот Хоккер.\n\n"
        "Чтобы получать уведомления и пользоваться меню, привяжите Telegram к аккаунту:\n"
        "1. Войдите в приложение 24hokker.ru\n"
        "2. Перейдите в Профиль → «Привязать Telegram»\n"
        "3. Нажмите кнопку — откроется этот бот"
    )
    markup = {"inline_keyboard": [[{"text": "🔗 Перейти на сайт", "url": app_url}]]}
    return reply(text_out, markup)


def _link_account(db: Session, chat_id: str, token_value: str, reply) -> dict:
    link = (
        db.query(TelegramLinkToken)
        .filter(TelegramLinkToken.token == token_value, TelegramLinkToken.used.is_(False))
        .first()
    )
    if link is None:
        return reply("Ссылка недействительна или уже использована. Сгенерируйте новую в приложении.")

    user = db.get(User, link.user_id)
    if user is None:
        return reply("Пользователь не найден.")

    already_taken = (
        db.query(User)
        .filter(User.telegram_chat_id == chat_id, User.id != user.id)
        .first()
    )
    if already_taken is not None:
        return reply(
            "Этот Telegram уже привязан к другому аккаунту 24hokker.ru. "
            "Если это ошибка — напишите в поддержку."
        )

    if user.telegram_chat_id != chat_id:
        user.telegram_chat_id = chat_id

    link.used = True
    link.used_at = datetime.now(timezone.utc)
    db.commit()

    return reply(
        f"✅ Готово, {esc(user.name)}! Telegram привязан к аккаунту 24hokker.ru.\n\n"
        "Сюда будут приходить уведомления о записях, заявках и тренировках. "
        "А кнопки ниже открывают нужные разделы приложения.",
        main_markup(role_of(user)),
    )
