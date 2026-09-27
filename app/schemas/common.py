def normalize_optional_text(v):
    """Убирает случайные пробелы по краям (и по всей строке, если она вся из
    пробелов) у необязательных текстовых полей вроде города. Используется как
    field_validator(mode="before") в схемах, куда город приходит от клиента.
    """
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v
