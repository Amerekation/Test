"""Доступ к БД Postgres (txpostgres).

Модуль инкапсулирует пул соединений и CRUD-операции над таблицей
`configurations`. Все вызовы асинхронные (Twisted/Deferred).
"""

from typing import Any, Dict, List, Optional, Tuple
import json

from txpostgres import txpostgres
from twisted.internet import defer

from app.settings import settings


# Пул соединений к Postgres. Запускается в `start_pool()`.
pool: txpostgres.ConnectionPool = txpostgres.ConnectionPool(
    None,
    dsn=settings.pg_dsn,
)


@defer.inlineCallbacks
def start_pool():
    """Стартует пул соединений к БД.

    Returns:
      Deferred: завершается после успешного старта пула.
    """
    yield pool.start()


@defer.inlineCallbacks
def stop_pool(_=None):
    """Корректно закрывает пул соединений к БД.

    Args:
      _ (Any): Не используется. Совместимость с хук-коллбэками.

    Returns:
      Deferred: завершается после закрытия пула.
    """
    yield pool.close()


def json_dumps(d: Dict[str, Any]) -> str:
    """Сериализует словарь в компактный JSON.

    Args:
      d (dict[str, Any]): Данные для сериализации.

    Returns:
      str: JSON-строка без лишних пробелов.
    """
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


@defer.inlineCallbacks
def insert_config(service: str, version: int, payload: Dict[str, Any]):
    """Вставляет конфигурацию сервиса.

    Args:
      service (str): Идентификатор сервиса.
      version (int): Номер версии.
      payload (dict[str, Any]): Тело конфигурации (JSON-совместимо).

    Returns:
      int: Идентификатор вставленной записи.
    """
    q = (
        "INSERT INTO configurations(service, version, payload) "
        "VALUES (%s, %s, %s::jsonb) RETURNING id;"
    )
    res = yield pool.runQuery(q, (service, version, json_dumps(payload)))
    defer.returnValue(res[0][0])


@defer.inlineCallbacks
def get_latest_version(service: str) -> Optional[int]:
    """Возвращает максимальную версию для сервиса.

    Args:
      service (str): Идентификатор сервиса.

    Returns:
      Optional[int]: Максимальная версия или None, если записей нет.
    """
    q = "SELECT MAX(version) FROM configurations WHERE service=%s"
    res = yield pool.runQuery(q, (service,))
    maxv = res[0][0]
    defer.returnValue(maxv if maxv is not None else None)


@defer.inlineCallbacks
def get_config(service: str, version: Optional[int]):
    """Читает конфигурацию сервиса.

    При `version=None` возвращает последнюю версию.

    Args:
      service (str): Идентификатор сервиса.
      version (Optional[int]): Номер версии или None.

    Returns:
      Optional[tuple[int, Any]]: Кортеж (version, payload) или None.
    """
    if version is None:
        q = (
            "SELECT version, payload FROM configurations "
            "WHERE service=%s ORDER BY version DESC LIMIT 1"
        )
        res = yield pool.runQuery(q, (service,))
    else:
        q = (
            "SELECT version, payload FROM configurations "
            "WHERE service=%s AND version=%s"
        )
        res = yield pool.runQuery(q, (service, version))
    defer.returnValue(res[0] if res else None)


@defer.inlineCallbacks
def get_history(service: str, limit: int = 20) -> List[Tuple[int, str]]:
    """Возвращает историю версий для сервиса.

    Args:
      service (str): Идентификатор сервиса.
      limit (int): Максимальное число элементов истории.

    Returns:
      list[tuple[int, str]]: Список (version, created_at_iso).
    """
    q = (
        "SELECT version, "
        "to_char(created_at AT TIME ZONE 'UTC', "
        "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
        "FROM configurations "
        "WHERE service=%s "
        "ORDER BY created_at DESC "
        "LIMIT %s"
    )
    res = yield pool.runQuery(q, (service, limit))
    defer.returnValue([(row[0], row[1]) for row in res])
