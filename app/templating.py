"""Шаблонизация конфигураций через Jinja2.

Модуль выполняет рекурсивный рендер конфигурации.
Рендерятся только строковые значения, которые содержат шаблонные
конструкции Jinja2 (`{{ ... }}` или `{% ... %}`).
Включён StrictUndefined, поэтому обращение к отсутствующим
переменным вызывает ошибку.
"""

from typing import Any, Dict

from jinja2 import Environment, StrictUndefined, TemplateError

env = Environment(undefined=StrictUndefined, autoescape=False)


def _render(val: Any, context: Dict[str, Any]) -> Any:
    """Рекурсивно рендерит значение с учётом типа.

    Если значение — строка и содержит шаблон, то оно
    рендерится через Jinja2. Списки и словари обходятся
    рекурсивно.

    Args:
      val: Значение произвольного типа.
      context: Контекст шаблона (переменные для подстановки).

    Returns:
      Any: Отрендеренное значение исходного типа.

    Raises:
      ValueError: Если Jinja2 не может отрендерить строку.
    """
    is_str = isinstance(val, str)
    has_tpl = is_str and ("{{" in val or "{%" in val)
    if has_tpl:
        try:
            return env.from_string(val).render(**context)
        except TemplateError as e:  # noqa: BLE001
            raise ValueError(
                f"Template render error: {e}"
            ) from e

    if isinstance(val, list):
        return [_render(x, context) for x in val]

    if isinstance(val, dict):
        return {k: _render(v, context) for k, v in val.items()}

    return val


def render_config(
    data: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Рендерит всю конфигурацию по заданному контексту.

    Обходит словарь целиком и рендерит только строковые
    значения, в которых есть шаблоны Jinja2.

    Args:
      data: Исходная конфигурация (словарь).
      context: Контекст шаблона (переменные).

    Returns:
      dict[str, Any]: Отрендерованная конфигурация.

    Raises:
      ValueError: Если произошла ошибка рендера.
    """
    rendered = _render(data, context)
    # Тип сохраняется словарём; _render возвращает Any.
    assert isinstance(rendered, dict)
    return rendered
