"""
Готовит иллюстрированную карточку упражнения к подключению:

  * WebP — для приложения (быстро грузится, ~250 КБ вместо ~1,7 МБ у PNG);
  * JPEG — для Telegram (родителю в чат приходит именно эта картинка;
    Telegram надёжнее всего принимает JPEG).

Файл должен называться по коду упражнения, как в каталоге: «ОФП-02.png».

Пример (из папки бэкенда; нужен Pillow: pip install pillow):

    python scripts/prepare_exercise_card.py "Каталог упражнений/ОФП-02.png" \
        --out ../hokker-frontend/public/exercise-cards

Скрипт создаёт ofp-02.webp и ofp-02.jpg и печатает SQL, который подключает
карточку к упражнению. После деплоя фронтенда выполните этот SQL в базе.
"""

import argparse
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Нужен Pillow: pip install pillow")

CODE_RE = re.compile(r"^ОФП-(\d+)$", re.IGNORECASE)


def prepare(src: Path, out_dir: Path) -> tuple[str, str]:
    match = CODE_RE.match(src.stem)
    if not match:
        raise ValueError(f"Имя файла «{src.name}» должно быть вида ОФП-02.png")
    number = int(match.group(1))
    code, slug = f"ОФП-{number:02d}", f"ofp-{number:02d}"

    image = Image.open(src).convert("RGB")
    out_dir.mkdir(parents=True, exist_ok=True)
    webp, jpg = out_dir / f"{slug}.webp", out_dir / f"{slug}.jpg"
    image.save(webp, "WEBP", quality=90, method=6)
    image.save(jpg, "JPEG", quality=88, optimize=True, progressive=True)

    kb = lambda p: f"{p.stat().st_size / 1024:.0f} КБ"
    print(f"{code}: {webp.name} ({kb(webp)}), {jpg.name} ({kb(jpg)})")
    return code, f"/exercise-cards/{slug}.webp"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path, help="PNG-карточки: ОФП-02.png …")
    parser.add_argument("--out", type=Path, default=Path("../hokker-frontend/public/exercise-cards"))
    args = parser.parse_args()

    statements = []
    for src in args.files:
        try:
            code, url = prepare(src, args.out)
        except ValueError as e:
            sys.exit(str(e))
        statements.append(f"UPDATE exercises SET image_url = '{url}' WHERE code = '{code}';")

    print("\nВыполните в базе после деплоя фронтенда:")
    print("\n".join(statements))


if __name__ == "__main__":
    main()
