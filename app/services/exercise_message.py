"""
Сообщение родителю «Тренер рекомендует отработать дома».

Что получает родитель:
  - если у упражнения есть иллюстрированная карточка (image_url) — саму
    картинку, а в подписи: кто рекомендует, комментарий тренера, название с
    кодом («ОФП-01 · Светофор»), описание и параметры;
  - если карточки нет — то же самое обычным текстом, плюс шаги «Как выполнять»
    (когда они есть);
  - в обоих случаях под сообщением кнопка «Открыть упражнение» — она ведёт на
    страницу именно этого упражнения в приложении.

Если Telegram не принял картинку (недоступен файл, неподдерживаемый формат),
уходит текстовый вариант — тренер не получает ошибку из-за того, что пострадало
только оформление. Если заблокировал бота сам родитель (HTTP 403), запасной
вариант не нужен: текст тоже не дойдёт, и ошибка честно уходит наверх.

Про формат картинки: Telegram надёжнее всего принимает JPEG, поэтому рядом с
карточкой для приложения (…/ofp-01.webp) лежит копия для Telegram (…/ofp-01.jpg).
Подготовить обе сразу: scripts/prepare_exercise_card.py.
"""

from app.models.exercise import Exercise
from app.services.telegram import (
    MAX_CAPTION_LEN,
    TelegramError,
    _webapp_supported,
    app_url,
    esc,
    open_app_markup,
    send_message_strict,
    send_photo_strict,
)

NO_EQUIPMENT = "Не требуется"


def telegram_photo_url(exercise: Exercise) -> str | None:
    """
    Публичный HTTPS-адрес JPEG-версии карточки для Telegram или None, если карточки
    нет. Без HTTPS (локальная разработка) Telegram всё равно не смог бы скачать файл.
    """
    if not exercise.image_url or not _webapp_supported():
        return None
    url = exercise.image_url
    if not url.startswith("http"):
        url = app_url(url)
    if url.lower().endswith(".webp"):
        url = url[: -len(".webp")] + ".jpg"
    return url


def _title(exercise: Exercise) -> str:
    return f"{exercise.code} · {exercise.title}" if exercise.code else exercise.title


def _meta(exercise: Exercise) -> str:
    parts = []
    if exercise.players_text:
        parts.append(f"👥 {esc(exercise.players_text)}")
    if exercise.duration_text:
        parts.append(f"⏱ {esc(exercise.duration_text)}")
    if exercise.equipment_text:
        if exercise.equipment_text == NO_EQUIPMENT:
            parts.append("🎒 инвентарь не нужен")
        else:
            parts.append(f"🎒 {esc(exercise.equipment_text)}")
    return " · ".join(parts)


def _compose(exercise, coach_name, note, *, with_description=True, with_meta=True, extras="") -> str:
    lines = [f"🏒 Тренер {esc(coach_name)} рекомендует отработать дома:"]
    if note:
        lines.append(f"💬 «{esc(note)}»")
    lines.append("")
    lines.append(f"<b>{esc(_title(exercise))}</b>")
    if with_description and exercise.description:
        lines.append(esc(exercise.description))
    if with_meta and _meta(exercise):
        lines.append(_meta(exercise))
    text = "\n".join(lines)
    return text + extras if extras else text


def build_caption(exercise: Exercise, coach_name: str, note: str | None) -> str:
    """Подпись к фото (≤ 1024 символов). Если не влезает — сначала жертвуем
    параметрами и описанием, потом сокращаем комментарий тренера."""
    caption = _compose(exercise, coach_name, note)
    if len(caption) <= MAX_CAPTION_LEN:
        return caption

    caption = _compose(exercise, coach_name, note, with_meta=False)
    if len(caption) <= MAX_CAPTION_LEN:
        return caption

    short_note = note or ""
    while short_note:
        short_note = short_note[: int(len(short_note) * 0.75)].rstrip()
        candidate = _compose(
            exercise,
            coach_name,
            (short_note + "…") if short_note else None,
            with_description=False,
            with_meta=False,
        )
        if len(candidate) <= MAX_CAPTION_LEN:
            return candidate
    return _compose(exercise, coach_name, None, with_description=False, with_meta=False)


def build_text(exercise: Exercise, coach_name: str, note: str | None) -> str:
    """Полный текст (без картинки): + шаги «Как выполнять» и ссылка на видео."""
    extras = ""
    if exercise.steps:
        extras += "\n\n<b>Как выполнять:</b>\n" + "\n".join(
            f"{i + 1}. {esc(step)}" for i, step in enumerate(exercise.steps)
        )
    if exercise.video_url:
        extras += f"\n\n▶️ {esc(exercise.video_url)}"
    return _compose(exercise, coach_name, note, extras=extras)


def send_exercise_to_chat(
    chat_id: str, exercise: Exercise, coach_name: str, note: str | None
) -> None:
    """Отправляет упражнение родителю. Бросает TelegramError, если не дошло совсем."""
    markup = open_app_markup("Открыть упражнение", f"/exercises/{exercise.id}")

    photo_url = telegram_photo_url(exercise)
    if photo_url:
        try:
            send_photo_strict(
                chat_id, photo_url, build_caption(exercise, coach_name, note), reply_markup=markup
            )
            return
        except TelegramError as e:
            if e.blocked:
                raise
            print(f"[TELEGRAM] карточка {exercise.code} не отправилась ({e}) — шлём текстом")

    send_message_strict(chat_id, build_text(exercise, coach_name, note), reply_markup=markup)
