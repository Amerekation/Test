"""Валидация входной конфигурации.

Модуль проверяет наличие обязательных полей и их типов, а также
выполняет дополнительные проверки значений (диапазон порта и
ненулевой host). Предназначен для первичной валидации YAML,
преобразованного в словарь.
"""

from typing import Any, Dict, List, Tuple, Optional

# Список обязательных полей и ожидаемых типов.
# Поле `version` опционально: если присутствует, должно быть int.
REQUIRED_FIELDS: List[Tuple[str, type]] = [
    ("version", int),
    ("database.host", str),
    ("database.port", int),
]


def _dig(d: Dict[str, Any], path: str) -> Optional[Any]:
    """Достаёт значение по «точечному» пути из словаря.

    Args:
      d: Исходный словарь.
      path: Путь вида "a.b.c".

    Returns:
      Значение по пути или None, если путь не существует.
    """
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def validate_config_payload(doc: Dict[str, Any]) -> List[str]:
    """Проверяет структуру и значения конфигурации.

    Проверяются:
      * наличие обязательных полей (кроме опционального `version`);
      * соответствие типов ожидаемым;
      * диапазон порта (1..65535);
      * непустой строковый `database.host`.

    Args:
      doc: Словарь конфигурации (из YAML).

    Returns:
      Список сообщений об ошибках. Пустой список означает, что
      конфигурация валидна.
    """
    errors: List[str] = []

    for path, expected_type in REQUIRED_FIELDS:
        val = _dig(doc, path)
        if val is None and path != "version":
            errors.append(f"Missing required field: {path}")
        elif val is not None and not isinstance(val, expected_type):
            exp = expected_type.__name__
            errors.append(f"Invalid type for {path}: expected {exp}")

    # Дополнительные проверки значений
    port = _dig(doc, "database.port")
    if isinstance(port, int) and not (1 <= port <= 65535):
        errors.append("Invalid database.port: must be 1..65535")

    host = _dig(doc, "database.host")
    if isinstance(host, str) and not host.strip():
        errors.append("Invalid database.host: must be non-empty string")

    return errors
