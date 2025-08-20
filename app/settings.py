"""Настройки приложения.

Читает переменные окружения `PG_DSN` и `PORT` и предоставляет
объект настроек для остальных модулей.
"""

from dataclasses import dataclass
import os


@dataclass
class Settings:
    """Конфигурация приложения.

    Attributes:
      pg_dsn: Строка подключения к Postgres.
      port: Порт HTTP-сервера.
    """

    pg_dsn: str = os.getenv(
        "PG_DSN",
        "dbname=configs user=postgres password=postgres "
        "host=db port=5432",
    )
    port: int = int(os.getenv("PORT", "8080"))


settings = Settings()
