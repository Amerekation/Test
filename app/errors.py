"""Пользовательские исключения для HTTP-ошибок.

Модуль содержит простые исключения, которые перехватываются в слое
API и маппятся на соответствующие HTTP-статусы.
"""


class BadRequest(Exception):
    """400 Bad Request.

    Выбрасывается при ошибках запроса: пустое тело, невалидный YAML,
    неверные параметры и т.п.
    """


class UnprocessableEntity(Exception):
    """422 Unprocessable Entity.

    Используется для ошибок валидации конфигурации и ошибок рендера
    шаблонов.

    Attributes:
      errors (list[str]): Список человекочитаемых сообщений об ошибках.
    """

    def __init__(self, errors: list[str]):
        """Создаёт исключение с набором ошибок.

        Args:
          errors (list[str]): Сообщения об ошибках.
        """
        super().__init__("; ".join(errors) if errors else "Unprocessable")
        self.errors = list(errors)


class NotFound(Exception):
    """404 Not Found.

    Сервис или версия конфигурации не найдены.
    """
