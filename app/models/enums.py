import enum


class UserRole(str, enum.Enum):
    coach = "coach"
    parent = "parent"
    arena_admin = "arena_admin"


class Specialization(str, enum.Enum):
    skating = "skating"          # катание
    shooting = "shooting"        # броски
    off_ice = "off_ice"          # ОФП
    goalie = "goalie"            # вратарская техника
    general = "general"          # общая подготовка


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


class SessionVisibility(str, enum.Enum):
    open = "open"
    closed = "closed"


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
