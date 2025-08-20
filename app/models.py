"""Pydantic-модели и валидация полей.

Содержит модели данных, используемые в API и вспомогательной
валидации. Используется Pydantic v2.
"""

from typing import Any, Dict

from pydantic import BaseModel, field_validator


class ConfigModel(BaseModel):
    """Обёртка над конфигурацией.

    Атрибуты:
      data (dict[str, Any]): Дерево конфигурации. Если поле
        `version` присутствует, оно обязано быть целым числом.
    """

    data: Dict[str, Any]

    @field_validator("data")
    @classmethod
    def version_type_if_present(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Проверяет, что `version`, если есть, имеет тип int.

        Args:
          v: Словарь конфигурации.

        Returns:
          dict[str, Any]: Исходные данные без изменений.

        Raises:
          ValueError: Если `version` присутствует и не является int.
        """
        if "version" in v and not isinstance(v["version"], int):
            raise ValueError("version must be integer")
        return v


class HistoryItem(BaseModel):
    """Элемент истории версий.

    Атрибуты:
      version (int): Номер версии.
      created_at (str): Время создания в ISO-формате.
    """

    version: int
    created_at: str  # ISO string
