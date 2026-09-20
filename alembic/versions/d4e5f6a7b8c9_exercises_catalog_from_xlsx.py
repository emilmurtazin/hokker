"""exercises catalog from Каталог упражнений.xlsx (ОФП-01 … ОФП-38)

Приводит каталог в соответствие с файлом «Каталог упражнений»:
  * названия, место (лёд / зал / вне льда), короткое описание, число игроков,
    время, инвентарь, «шайба» и развиваемые качества — по карточкам;
  * возраст у всех карточек — 6–9 (как в возрастных категориях приложения),
    хотя на самих карточках указано «7–9» / «7–10»;
  * упражнения ОФП-31…38 добавляются, ОФП-06…30 переименовываются: прежний
    сид содержал другой список (например, ОФП-06 был «Старт по сигналу»,
    а по файлу это «Пятнашки»);
  * пошаговые инструкции, подсказки, «упростить/усложнить» и «связь с хоккеем»
    (есть у ОФП-01…05) НЕ трогаем;
  * для ОФП-01 подключается иллюстрированная карточка (image_url).

Обновление идёт по коду (code): изменения, сделанные вручную через админку в
записях ОФП-01…38, будут перезаписаны данными из файла.

Downgrade убирает добавленные ОФП-31…38 и снимает image_url у ОФП-01;
прежние названия ОФП-06…30 не восстанавливаются.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-20 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


exercises_table = sa.table(
    "exercises",
    sa.column("code", sa.String),
    sa.column("title", sa.String),
    sa.column("description", sa.Text),
    sa.column("category", sa.String),
    sa.column("location", sa.String),
    sa.column("age_group", sa.String),
    sa.column("players_text", sa.String),
    sa.column("duration_text", sa.String),
    sa.column("equipment_text", sa.String),
    sa.column("needs_puck", sa.Boolean),
    sa.column("qualities", ARRAY(sa.String(50))),
    sa.column("content_status", sa.String),
    sa.column("image_url", sa.String),
)

# Иллюстрированная карточка ОФП-01 лежит во фронтенде: public/exercise-cards/ofp-01.webp
CARD_IMAGES = {"ОФП-01": "/exercise-cards/ofp-01.webp"}

# Возраст в БД хранится как имя enum-члена (age_6_9), см. модель ExerciseAgeGroup.
AGE_GROUP = "age_6_9"

CATALOG = [
    dict(
        code='ОФП-01',
        title='Светофор',
        location='on_ice',
        description='Развиваем реакцию, контроль скорости и умение быстро останавливаться по сигналу.',
        players_text='4–10',
        duration_text='5 минут',
        equipment_text='3 цветные карточки или маркера',
        needs_puck=False,
        qualities=['Реакция', 'Скорость', 'Баланс', 'Смена направления', 'Контроль тела'],
    ),
    dict(
        code='ОФП-02',
        title='Линия вправо-влево',
        location='on_ice',
        description='Развиваем быстроту ног, координацию и баланс.',
        players_text='1–6',
        duration_text='4 минуты',
        equipment_text='Разметка льда (линия)',
        needs_puck=False,
        qualities=['Координация', 'Баланс', 'Быстрота ног', 'Контроль тела'],
    ),
    dict(
        code='ОФП-03',
        title='Вперёд-назад',
        location='on_ice',
        description='Развиваем контроль движения, координацию и баланс.',
        players_text='1–6',
        duration_text='4 минуты',
        equipment_text='Разметка льда (линия)',
        needs_puck=False,
        qualities=['Координация', 'Баланс', 'Ориентация', 'Контроль тела', 'Реакция'],
    ),
    dict(
        code='ОФП-04',
        title='Зеркало',
        location='on_ice',
        description='Развиваем реакцию, внимание и способность быстро менять направление.',
        players_text='2',
        duration_text='4–5 минут',
        equipment_text='Не требуется',
        needs_puck=False,
        qualities=['Реакция', 'Внимание', 'Координация', 'Ловкость', 'Смена направления'],
    ),
    dict(
        code='ОФП-05',
        title='Цветные острова',
        location='on_ice',
        description='Развиваем реакцию, скорость и способность быстро менять направление.',
        players_text='4–8',
        duration_text='5 минут',
        equipment_text='4–6 цветных конусов',
        needs_puck=False,
        qualities=['Реакция', 'Скорость', 'Ловкость', 'Ориентация', 'Смена направления'],
    ),
    dict(
        code='ОФП-06',
        title='Пятнашки',
        location='on_ice',
        description='Развиваем ловкость, ускорение и умение действовать по сигналу.',
        players_text='3–6',
        duration_text='5 минут',
        equipment_text='6–9 цветных фишек (пятен)',
        needs_puck=False,
        qualities=['Реакция', 'Скорость', 'Координация', 'Внимание', 'Смена направления'],
    ),
    dict(
        code='ОФП-07',
        title='Замри',
        location='on_ice',
        description='Развиваем умение быстро останавливаться и контролировать положение тела.',
        players_text='4–10',
        duration_text='5 минут',
        equipment_text='Не требуется',
        needs_puck=False,
        qualities=['Торможение', 'Баланс', 'Контроль тела', 'Реакция', 'Внимание'],
    ),
    dict(
        code='ОФП-08',
        title='Змейка без шайбы',
        location='on_ice',
        description='Развиваем координацию, ловкость и умение быстро менять направление.',
        players_text='1–6',
        duration_text='5 минут',
        equipment_text='4–6 конусов',
        needs_puck=False,
        qualities=['Координация', 'Смена направления', 'Баланс', 'Ловкость', 'Скорость'],
    ),
    dict(
        code='ОФП-09',
        title='Челночный бег',
        location='on_ice',
        description='Развиваем скорость, выносливость, способность быстро разгоняться и тормозить.',
        players_text='3–8',
        duration_text='5–7 минут',
        equipment_text='4 конуса',
        needs_puck=False,
        qualities=['Скорость', 'Выносливость', 'Координация', 'Реакция', 'Ловкость'],
    ),
    dict(
        code='ОФП-10',
        title='Ускорения 10 метров',
        location='on_ice',
        description='Развиваем стартовую скорость, ускорение и взрывную силу.',
        players_text='3–8',
        duration_text='5–7 минут',
        equipment_text='2 конуса',
        needs_puck=False,
        qualities=['Скорость', 'Ускорение', 'Взрывная сила', 'Стартовая реакция', 'Координация'],
    ),
    dict(
        code='ОФП-11',
        title='Лягушка',
        location='gym',
        description='Развиваем силу ног, взрывную силу и координацию.',
        players_text='1–6',
        duration_text='4–6 минут',
        equipment_text='3 конуса или метки',
        needs_puck=None,
        qualities=['Сила ног', 'Взрывная сила', 'Координация', 'Баланс', 'Мощность'],
    ),
    dict(
        code='ОФП-12',
        title='Выпады с прыжком',
        location='gym',
        description='Развиваем силу ног, взрывную силу, равновесие и координацию.',
        players_text='1–6',
        duration_text='5–7 минут',
        equipment_text='Коврик (по желанию)',
        needs_puck=None,
        qualities=['Сила ног', 'Взрывная сила', 'Координация', 'Равновесие', 'Выносливость'],
    ),
    dict(
        code='ОФП-13',
        title='Планка на локтях',
        location='gym',
        description='Развиваем силу кора, выносливость и стабилизацию корпуса.',
        players_text='1–6',
        duration_text='20–40 секунд',
        equipment_text='Коврик (по желанию)',
        needs_puck=None,
        qualities=['Сила кора', 'Выносливость', 'Стабильность', 'Устойчивость', 'Концентрация'],
    ),
    dict(
        code='ОФП-14',
        title='Бёрпи',
        location='gym',
        description='Развиваем выносливость, взрывную силу, координацию и силу всего тела.',
        players_text='1–6',
        duration_text='30–60 секунд',
        equipment_text='Коврик (по желанию)',
        needs_puck=None,
        qualities=['Выносливость', 'Взрывная сила', 'Координация', 'Сила мышц', 'Скорость'],
    ),
    dict(
        code='ОФП-15',
        title='Краб',
        location='gym',
        description='Развиваем силу рук и плечевого пояса, мышц кора и координацию.',
        players_text='1–6',
        duration_text='30–60 секунд',
        equipment_text='Коврик (по желанию)',
        needs_puck=None,
        qualities=['Сила кора', 'Сила рук', 'Стабильность', 'Координация', 'Выносливость'],
    ),
    dict(
        code='ОФП-16',
        title='Скачки на месте',
        location='gym',
        description='Развиваем выносливость, координацию, силу ног и сердечно-сосудистую систему.',
        players_text='1–6',
        duration_text='20–40 секунд',
        equipment_text='Коврик (по желанию)',
        needs_puck=None,
        qualities=['Выносливость', 'Скорость', 'Координация', 'Сила ног', 'Сердечно-сосудистая система'],
    ),
    dict(
        code='ОФП-17',
        title='Выпады на месте',
        location='gym',
        description='Развиваем силу ног, ягодиц и стабилизацию тела, улучшаем координацию и выносливость.',
        players_text='1–6',
        duration_text='30–60 секунд',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Сила ног', 'Координация', 'Выносливость', 'Стабильность', 'Устойчивость'],
    ),
    dict(
        code='ОФП-18',
        title='Приседания на одной ноге',
        location='gym',
        description='Развиваем силу ног, баланс, координацию и устойчивость корпуса.',
        players_text='1–6',
        duration_text='30–60 секунд на ногу',
        equipment_text='Стойка, стул (при необходимости)',
        needs_puck=None,
        qualities=['Сила ног', 'Баланс', 'Координация', 'Устойчивость', 'Общая выносливость'],
    ),
    dict(
        code='ОФП-19',
        title='Выпады в движении',
        location='gym',
        description='Развиваем силу ног, баланс, координацию и выносливость.',
        players_text='1–6',
        duration_text='30–60 секунд на ногу',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Сила ног', 'Баланс', 'Координация', 'Устойчивость', 'Выносливость'],
    ),
    dict(
        code='ОФП-20',
        title='Подъём на носки',
        location='gym',
        description='Укрепляем икры, стопы и голеностопы, развиваем силу и выносливость.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Сила ног', 'Баланс', 'Выносливость', 'Устойчивость', 'Контроль на льду'],
    ),
    dict(
        code='ОФП-21',
        title='Приседания с выпрыгиванием',
        location='gym',
        description='Развиваем силу ног, взрывную силу, выносливость и координацию.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Сила ног', 'Взрывная сила', 'Координация', 'Выносливость', 'Скорость'],
    ),
    dict(
        code='ОФП-22',
        title='Медвежья прогулка',
        location='gym',
        description='Развиваем силу корпуса, координацию и выносливость.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Сила корпуса', 'Координация', 'Выносливость'],
    ),
    dict(
        code='ОФП-23',
        title='Прыжки через линию',
        location='gym',
        description='Развиваем быстроту ног, координацию и чувство ритма.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Быстрота ног', 'Координация', 'Баланс'],
    ),
    dict(
        code='ОФП-24',
        title='Самолёт',
        location='gym',
        description='Развиваем баланс, контроль корпуса.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Баланс', 'Контроль корпуса', 'Устойчивость'],
    ),
    dict(
        code='ОФП-25',
        title='Бег по цвету',
        location='gym',
        description='Развиваем реакцию, скорость и смену направления.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='Цветные конусы или метки',
        needs_puck=None,
        qualities=['Реакция', 'Скорость', 'Смена направления'],
    ),
    dict(
        code='ОФП-26',
        title='Четыре конуса',
        location='gym',
        description='Развиваем координацию, скорость и внимание.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='4 конуса',
        needs_puck=None,
        qualities=['Координация', 'Быстрота', 'Внимание'],
    ),
    dict(
        code='ОФП-27',
        title='Полоса ловкости',
        location='gym',
        description='Развиваем координацию, ловкость, скорость и выносливость.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='Лестница, конусы, барьеры, обручи',
        needs_puck=None,
        qualities=['Ловкость', 'Координация', 'Быстрота', 'Выносливость'],
    ),
    dict(
        code='ОФП-28',
        title='Старт из разных положений',
        location='gym',
        description='Развиваем скорость реакции, взрывную силу и координацию.',
        players_text='1–6',
        duration_text='30–60 секунд на подход',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Скорость', 'Реакция', 'Координация', 'Взрывная сила'],
    ),
    dict(
        code='ОФП-29',
        title='Баланс на одной ноге',
        location='off_ice',
        description='Развиваем равновесие, координацию и устойчивость.',
        players_text='1',
        duration_text='20–40 секунд на каждую ногу',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Равновесие', 'Координация', 'Устойчивость', 'Стабильность'],
    ),
    dict(
        code='ОФП-30',
        title='Мяч вокруг тела',
        location='off_ice',
        description='Развиваем координацию, ловкость, гибкость и чувство тела.',
        players_text='1',
        duration_text='30–45 секунд на каждую сторону',
        equipment_text='Мяч (теннисный, футбольный или гимнастический)',
        needs_puck=None,
        qualities=['Координация', 'Ловкость', 'Гибкость', 'Контроль тела'],
    ),
    dict(
        code='ОФП-31',
        title='Поймай мяч',
        location='off_ice',
        description='Развиваем реакцию, координацию, ловкость и внимание.',
        players_text='1 и более',
        duration_text='30–60 секунд на подход',
        equipment_text='Мяч (теннисный, футбольный, баскетбольный и др.)',
        needs_puck=None,
        qualities=['Реакция', 'Координация', 'Ловкость', 'Внимание'],
    ),
    dict(
        code='ОФП-32',
        title='Мяч — правая / левая',
        location='off_ice',
        description='Развиваем координацию, ловкость, точность и контроль движений.',
        players_text='1',
        duration_text='30–45 секунд на упражнение',
        equipment_text='Мяч',
        needs_puck=None,
        qualities=['Координация', 'Ловкость', 'Точность', 'Контроль'],
    ),
    dict(
        code='ОФП-33',
        title='Зеркало',
        location='off_ice',
        description='Развиваем координацию, внимание, реакцию и чувство партнёра.',
        players_text='2 и более',
        duration_text='30–60 секунд на подход',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Координация', 'Внимание', 'Реакция', 'Командная работа'],
    ),
    dict(
        code='ОФП-34',
        title='Цветная реакция',
        location='off_ice',
        description='Развиваем внимание, скорость реакции, координацию и умение ориентироваться по сигналу.',
        players_text='2 и более',
        duration_text='30–45 секунд на упражнение',
        equipment_text='Цветные карточки или конусы',
        needs_puck=None,
        qualities=['Реакция', 'Внимание', 'Координация', 'Умение ориентироваться'],
    ),
    dict(
        code='ОФП-35',
        title='Прыжок — остановка',
        location='off_ice',
        description='Развиваем силу, координацию, реакцию, контроль тела и умение быстро останавливаться.',
        players_text='1 и более',
        duration_text='30–45 секунд на подход',
        equipment_text='Не требуется',
        needs_puck=None,
        qualities=['Сила', 'Координация', 'Реакция', 'Равновесие'],
    ),
    dict(
        code='ОФП-36',
        title='Ловкий квадрат',
        location='off_ice',
        description='Развиваем ловкость, быстроту реакции, координацию и умение ориентироваться в пространстве.',
        players_text='2 и более',
        duration_text='30–45 секунд на упражнение',
        equipment_text='Квадраты (лента, мел, конусы)',
        needs_puck=None,
        qualities=['Ловкость', 'Координация', 'Реакция', 'Внимание'],
    ),
    dict(
        code='ОФП-37',
        title='Реактивный старт',
        location='off_ice',
        description='Развиваем взрывную силу, скорость реакции и стартовую динамику.',
        players_text='2 и более',
        duration_text='30–45 секунд на подход',
        equipment_text='Конусы, свисток (или хлопок)',
        needs_puck=None,
        qualities=['Скорость', 'Реакция', 'Взрывная сила', 'Координация'],
    ),
    dict(
        code='ОФП-38',
        title='Домашняя полоса',
        location='off_ice',
        description='Развиваем выносливость, ловкость, координацию и умение преодолевать препятствия.',
        players_text='1 и более',
        duration_text='30–45 секунд на каждый этап',
        equipment_text='Подушки, стулья, палки, обручи, конусы (или предметы дома)',
        needs_puck=None,
        qualities=['Выносливость', 'Координация', 'Ловкость', 'Уверенность в движении'],
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for row in CATALOG:
        fields = dict(row, category="strength", age_group=AGE_GROUP)
        code = fields.pop("code")
        result = conn.execute(
            exercises_table.update().where(exercises_table.c.code == code).values(**fields)
        )
        if result.rowcount == 0:
            # Новое упражнение (ОФП-31…38): пока только краткая карточка.
            conn.execute(
                exercises_table.insert().values(code=code, content_status="draft", **fields)
            )

    for code, url in CARD_IMAGES.items():
        conn.execute(
            exercises_table.update().where(exercises_table.c.code == code).values(image_url=url)
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        exercises_table.update()
        .where(exercises_table.c.code.in_(list(CARD_IMAGES)))
        .values(image_url=None)
    )
    new_codes = [row["code"] for row in CATALOG if int(row["code"].split("-")[1]) > 30]
    conn.execute(exercises_table.delete().where(exercises_table.c.code.in_(new_codes)))
