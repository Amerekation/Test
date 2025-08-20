"""HTTP API для сервиса управления конфигурациями.

Сервис предоставляет REST-эндпоинты для загрузки, чтения и рендера
конфигураций, а также получения истории версий. Реализация выполнена
на Twisted/Klein с неблокирующим доступом к Postgres (txpostgres).
"""

from typing import Any, Dict

import json
import yaml
from klein import Klein
from twisted.internet import defer, reactor
from twisted.web.server import Site

from app.errors import (
    BadRequest,
    NotFound,
    UnprocessableEntity,
)
from app.settings import settings
from app.templating import render_config
from app.validation import validate_config_payload
from app.db import (
    get_config,
    get_history,
    get_latest_version,
    insert_config,
    pool,
    start_pool,
    stop_pool,
)

app = Klein()


def _json(
    request,
    status: int = 200,
    body: Dict[str, Any] | list | None = None,
):
    """Сериализует ответ в JSON и проставляет заголовки.

    Args:
      request: Объект Klein/Twisted запроса.
      status (int): Код HTTP-статуса.
      body (dict | list | None): Тело ответа.

    Returns:
      bytes: JSON-представление тела ответа.
    """
    request.setHeader(
        b"Content-Type",
        b"application/json; charset=utf-8",
    )
    request.setResponseCode(status)
    payload = body if body is not None else {}
    return json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")


def _read_body(request) -> bytes:
    """Читает сырое тело запроса.

    Args:
      request: Объект Klein/Twisted запроса.

    Returns:
      bytes: Контент тела (или b'' если пусто).
    """
    return request.content.read() or b""


@app.handle_errors(
    BadRequest,
    UnprocessableEntity,
    NotFound,
    Exception,
)
def _handle_errors(request, failure):
    """Единая обработка исключений и маппинг в HTTP-коды.

    Args:
      request: Объект запроса.
      failure: Twisted Failure с исходным исключением.

    Returns:
      bytes: JSON с описанием ошибки.
    """
    err = failure.value
    if isinstance(err, BadRequest):
        return _json(request, 400, {"error": str(err)})
    if isinstance(err, UnprocessableEntity):
        return _json(request, 422, {"errors": err.errors})
    if isinstance(err, NotFound):
        return _json(request, 404, {"error": "service not found"})
    return _json(request, 500, {"error": "internal server error"})


# ---------- Service endpoints --------------------------------------


@app.route("/config/<service>", methods=["POST"])
@defer.inlineCallbacks
def post_config(request, service: str):
    """Создаёт новую версию конфигурации для сервиса.

    Тело запроса — YAML. Поля `database.host` и `database.port`
    обязательны. Если `version` не указана, она назначается как
    `max(version)+1`.

    Args:
      request: Объект запроса.
      service (str): Идентификатор сервиса.

    Returns:
      bytes: JSON с полями `service`, `version`, `status`.

    Raises:
      BadRequest: Невалидный YAML или пустое тело.
      UnprocessableEntity: Конфигурация не прошла валидацию.
    """
    raw = _read_body(request)
    if not raw:
        raise BadRequest("empty body")

    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except yaml.YAMLError as e:
        raise BadRequest(f"YAML parse error: {e}")

    if not isinstance(data, dict):
        raise BadRequest("YAML must represent a mapping (object)")

    errors = validate_config_payload(data)
    if errors:
        raise UnprocessableEntity(errors)

    version = data.get("version")
    if version is None:
        maxv = yield get_latest_version(service)
        version = 1 if maxv is None else maxv + 1
        data["version"] = version

    _ = yield insert_config(service, version, data)
    body = {"service": service, "version": version, "status": "saved"}
    defer.returnValue(_json(request, 200, body))


@app.route("/config/<service>", methods=["GET"])
@defer.inlineCallbacks
def get_config_route(request, service: str):
    """Возвращает конфигурацию сервиса.

    Без параметров вернёт последнюю версию. Поддерживаются:
      * `version=N` — конкретная версия;
      * `template=1` — рендер значений через Jinja2. Контекст
        берётся из JSON-тела запроса (для совместимости с ТЗ).

    Args:
      request: Объект запроса.
      service (str): Идентификатор сервиса.

    Returns:
      bytes: JSON-объект конфигурации.

    Raises:
      BadRequest: Некорректный `version` или контекст шаблона.
      NotFound: Сервис/версия не найдены.
      UnprocessableEntity: Ошибка рендера шаблона.
    """
    args = request.args
    version = None
    if b"version" in args:
        try:
            version = int(args[b"version"][0].decode())
        except ValueError:
            raise BadRequest("version must be integer")

    row = yield get_config(service, version)
    if not row:
        raise NotFound()

    _ver, payload = row
    if isinstance(payload, (bytes, bytearray)):
        payload = json.loads(payload.decode())
    elif isinstance(payload, str):
        payload = json.loads(payload)
    elif not isinstance(payload, dict):
        payload = json.loads(json.dumps(payload))

    if args.get(b"template", [b"0"])[0] == b"1":
        ctx_bytes = _read_body(request)
        context = {}
        if ctx_bytes:
            try:
                context = json.loads(ctx_bytes.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise BadRequest(
                    f"Invalid JSON body for template context: {e}"
                )
        try:
            payload = render_config(payload, context)
        except ValueError as e:
            raise UnprocessableEntity([str(e)])

    defer.returnValue(_json(request, 200, payload))


@app.route("/config/<service>/history", methods=["GET"])
@defer.inlineCallbacks
def get_history_route(request, service: str):
    """Возвращает историю версий конфигурации.

    Args:
      request: Объект запроса.
      service (str): Идентификатор сервиса.

    Returns:
      bytes: JSON-массив объектов `{version, created_at}`.
    """
    items = yield get_history(service, limit=50)
    body = [{"version": v, "created_at": ts} for v, ts in items]
    defer.returnValue(_json(request, 200, body))


# ---------- Convenience endpoints ----------------------------------


@app.route("/", methods=["GET"])
def index(request):
    """Индекс-страница со списком эндпоинтов.

    Args:
      request: Объект запроса.

    Returns:
      bytes: JSON со списком поддерживаемых путей.
    """
    return _json(
        request,
        200,
        {
            "status": "ok",
            "endpoints": [
                "POST /config/<service>",
                "GET  /config/<service>?version=N&template=1",
                "GET  /config/<service>/history",
                "POST /config/<service>/render?version=N",
                "GET  /health",
            ],
        },
    )


@app.route("/health", methods=["GET"])
@defer.inlineCallbacks
def health(request):
    """Простой healthcheck с проверкой соединения с БД.

    Args:
      request: Объект запроса.

    Returns:
      bytes: `{\"status\":\"ok\"}` или описание ошибки.
    """
    try:
        yield pool.runQuery("SELECT 1")
        defer.returnValue(_json(request, 200, {"status": "ok"}))
    except Exception as e:  # noqa: BLE001
        defer.returnValue(
            _json(
                request,
                500,
                {"status": "error", "detail": str(e)},
            )
        )


@app.route("/config/<service>/render", methods=["POST"])
@defer.inlineCallbacks
def render_config_route(request, service: str):
    """Рендер конфигурации через POST.

    Контекст шаблона передаётся в JSON-теле запроса. Версия выбирается
    параметром `version` в query.

    Args:
      request: Объект запроса.
      service (str): Идентификатор сервиса.

    Returns:
      bytes: JSON сконфигурированного объекта.

    Raises:
      BadRequest: Некорректная версия или JSON-контекст.
      NotFound: Сервис/версия не найдены.
      UnprocessableEntity: Ошибка рендера.
    """
    args = request.args
    version = None
    if b"version" in args:
        try:
            version = int(args[b"version"][0].decode())
        except ValueError:
            raise BadRequest("version must be integer")

    row = yield get_config(service, version)
    if not row:
        raise NotFound()

    _ver, payload = row
    if isinstance(payload, (bytes, bytearray)):
        payload = json.loads(payload.decode())
    elif isinstance(payload, str):
        payload = json.loads(payload)

    raw = _read_body(request)
    try:
        context = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError as e:
        raise BadRequest(
            f"Invalid JSON body for template context: {e}"
        )

    try:
        rendered = render_config(payload, context)
    except ValueError as e:
        raise UnprocessableEntity([str(e)])

    defer.returnValue(_json(request, 200, rendered))


# ---------- Runner --------------------------------------------------


def run():
    """Запускает приложение: БД-пул, HTTP-сервер и Twisted reactor."""
    d = start_pool()

    def _started(_):
        print(f"Listening on 0.0.0.0:{settings.port}")
        site = Site(app.resource())
        reactor.listenTCP(settings.port, site)

    d.addCallback(_started)
    reactor.addSystemEventTrigger("before", "shutdown", stop_pool)
    reactor.run()


if __name__ == "__main__":
    run()
