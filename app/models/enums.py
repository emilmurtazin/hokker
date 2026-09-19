import enum


class UserRole(str, enum.Enum):
    coach = "coach"
    parent = "parent"
    arena_admin = "arena_admin"
    admin = "admin"  # платформенный администратор — управляет библиотекой видеоупражнений


class ExerciseCategory(str, enum.Enum):
    skating = "skating"                # техника катания
    stickhandling = "stickhandling"    # техника ведения шайбы
    shooting = "shooting"              # техника броска
    strength = "strength"              # силовые тренировки (ОФП)
    goalie = "goalie"                  # вратарская техника
    game = "game"                      # игровые упражнения


class ExerciseAgeGroup(str, enum.Enum):
    age_6_9 = "6-9"
    age_10_12 = "10-12"
    age_13_plus = "13+"


class ExerciseLevel(str, enum.Enum):
    beginner = "beginner"          # новичок
    intermediate = "intermediate"  # средний
    advanced = "advanced"          # продвинутый


class ExerciseLocation(str, enum.Enum):
    on_ice = "on_ice"      # на льду
    gym = "gym"            # в зале
    off_ice = "off_ice"    # вне льда (дома)


class ExerciseContentStatus(str, enum.Enum):
    complete = "complete"  # карточка заполнена полностью
    draft = "draft"        # есть только название и качества, описание в работе


class Specialization(str, enum.Enum):
    ice = "ice"
    off_ice = "off_ice"
    shooting = "shooting"
    theory = "theory"
    game = "game"
    goalie = "goalie"


class Position(str, enum.Enum):
    forward = "forward"
    defense = "defense"
    goalie = "goalie"


class CoachPlayerStatus(str, enum.Enum):
    active = "active"
    pending = "pending"
    removed = "removed"


class SessionType(str, enum.Enum):
    ice = "ice"
    off_ice = "off_ice"
    shooting = "shooting"
    theory = "theory"
    game = "game"
    goalie = "goalie"


class SessionVisibility(str, enum.Enum):
    open = "open"
    closed = "closed"


class IceType(str, enum.Enum):
    full = "full"     # полный лёд
    half = "half"     # половина
    third = "third"   # треть


class SlotStatus(str, enum.Enum):
    available = "available"
    pending = "pending"
    booked = "booked"
    cancelled = "cancelled"


class SlotRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled_by_coach = "cancelled_by_coach"


class SkillCategory(str, enum.Enum):
    skating = "skating"                # катание
    stickhandling = "stickhandling"    # владение клюшкой
    shooting = "shooting"              # бросок
    tactics = "tactics"                # тактика
    discipline = "discipline"          # дисциплина


class AttendanceStatus(str, enum.Enum):
    present = "present"       # присутствовал
    absent = "absent"         # отсутствовал
    sick = "sick"              # болел
    no_reason = "no_reason"    # без причины


class BookingStatus(str, enum.Enum):
    pending = "pending"        # ждёт подтверждения тренера (новый клиент)
    confirmed = "confirmed"    # подтверждено, место занято
    waiting = "waiting"        # в листе ожидания
    invited = "invited"        # приглашён с листа ожидания, ждёт подтверждения (15 мин)
    cancelled = "cancelled"    # отменено родителем
    rejected = "rejected"      # отклонено тренером
    expired = "expired"        # не подтвердил приглашение вовремя
