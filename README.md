# Test — Сервис управления конфигурациями (Twisted + Postgres)

Сервис для хранения и выдачи конфигураций распределённых сервисов.
Поддерживает версионирование, шаблоны (Jinja2), историю и запуск через Docker.

---

## Быстрый старт (Docker)

```bash
docker compose up -d --build
# проверка здоровья
curl -sS http://localhost:8080/health
```

После старта приложение слушает `http://localhost:8080`.

> Примечание: предупреждение Compose `the attribute 'version' is obsolete` можно игнорировать
> или удалить строку `version: "3.9"` из `docker-compose.yml`.

---

## Переменные окружения

* `PG_DSN` — строка подключения к Postgres
  по умолчанию: `dbname=configs user=postgres password=postgres host=db port=5432`
* `PORT` — порт приложения (по умолчанию `8080`)

---

## Эндпоинты

### `GET /` — индекс

Простая проверка: возвращает список доступных эндпоинтов.

```bash
curl -sS http://localhost:8080/
```

### `GET /health` — healthcheck (проверка БД)

Возвращает `{"status":"ok"}` если соединение с БД успешно.

```bash
curl -sS http://localhost:8080/health
```

---

### `POST /config/{service}` — загрузить конфиг (YAML)

Тело запроса — **YAML**. Проверяются обязательные поля:

* `database.host` (строка)
* `database.port` (целое 1..65535)
* `version` (если указан — целое; если отсутствует — назначится автоматически `max(version)+1`)

**Ответ (пример):**

```json
{ "service": "my_service", "version": 1, "status": "saved" }
```

**Пример запроса:**

```bash
curl -sS -X POST http://localhost:8080/config/my_service \
  -H "Content-Type: text/yaml" \
  --data-binary @- <<'YAML'
database:
  host: "db.local"
  port: 5432
features:
  enable_auth: true
  enable_cache: false
YAML
```

**Ошибки:**

* Невалидный YAML → `400 Bad Request`
* Не прошла валидация полей → `422 Unprocessable Entity` + список ошибок

---

### `GET /config/{service}` — получить конфиг

Параметры:

* `?version=N` — вернуть конкретную версию (по умолчанию — последняя)
* `?template=1` — отрендерить строки через Jinja2
  **Контекст шаблона** передаётся **JSON в теле GET** (нестандартно, но поддержано как в ТЗ)

**Примеры:**

```bash
# последняя версия как есть (без рендера)
curl -sS http://localhost:8080/config/my_service

# конкретная версия
curl -sS "http://localhost:8080/config/my_service?version=1"

# рендер через GET (обязательно явно -X GET, иначе curl превратит в POST)
curl -sS -X GET "http://localhost:8080/config/my_service?template=1" \
  -H "Content-Type: application/json" \
  --data '{"user":"Alice"}'
```

---

### `POST /config/{service}/render?version=N` — **рекомендуемый рендер** через POST

Удобная альтернатива `?template=1`. Контекст передаётся в **JSON-теле POST**.

```bash
curl -sS -X POST "http://localhost:8080/config/my_service/render?version=2" \
  -H "Content-Type: application/json" \
  --data '{"user":"Alice"}'
```

**Пример результата:**

```json
{
  "version": 2,
  "database": {"host":"db.local","port":5432},
  "welcome_message": "Hello Alice!"
}
```

---

### `GET /config/{service}/history` — история версий

Возвращает массив:

```json
[
  {"version": 1, "created_at": "2025-08-19T12:00:00Z"},
  {"version": 2, "created_at": "2025-08-19T12:15:00Z"}
]
```

```bash
curl -sS http://localhost:8080/config/my_service/history
```

---

## Формат конфигурации

**Вход (YAML):**

```yaml
version: 1
database:
  host: "db.local"
  port: 5432
features:
  enable_auth: true
  enable_cache: false
```

**Шаблоны (Jinja2):**

```yaml
version: 2
welcome_message: "Hello {{ user }}!"
```

---

## Хранилище (Postgres)

Таблица `configurations`:

* `id` (serial, PK)
* `service` (text, not null)
* `version` (integer, not null, **уникальна в паре** с `service`)
* `payload` (jsonb, not null) — конфигурация в JSON
* `created_at` (timestamptz, default now())

Уникальный индекс: `(service, version)`.

---

## Локальный запуск без Docker (опционально)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# локальный Postgres (или через Docker):
# docker run --rm -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=configs -p 5432:5432 -d postgres:16

export PG_DSN="dbname=configs user=postgres password=postgres host=localhost port=5432"
export PORT=8080

# миграция
psql -h localhost -U postgres -d configs -f app/migrations/001_init.sql

# старт
python -m app.api
```

---

## Структура проекта

```
app/
  api.py           # эндпоинты (Klein/Twisted)
  db.py            # неблокирующий доступ к БД (txpostgres)
  validation.py    # проверка обязательных полей
  templating.py    # рекурсивный рендер Jinja2
  settings.py      # конфиг приложения
  errors.py        # исключения -> HTTP коды
  migrations/
    001_init.sql
Dockerfile
docker-compose.yml
README.md
```

---

## Коды ошибок

* `400 Bad Request` — невалидный YAML / неверные параметры запроса
* `422 Unprocessable Entity` — валидация полей / ошибка рендера шаблона
* `404 Not Found` — сервис/версия не найдены
* `500 Internal Server Error` — непредвиденная ошибка

---

## Траблшутинг

* **Нет доступа к Docker-сокету**: `permission denied /var/run/docker.sock`
  Добавьте пользователя в группу `docker` и перезапустите/перелогиньтесь:

  ```bash
  sudo usermod -aG docker $USER && newgrp docker
  ```
* **Порт занят**: поменяйте левую часть в `ports` для `app` (например, `9090:8080`) и обращайтесь по `http://localhost:9090`.
* **GET с телом не рендерит**: убедитесь, что используете `-X GET` (или используйте удобный `POST /config/{service}/render?version=N`).

---

## Идеи для улучшений

* Ретраи при автоназначении версии на конфликте уникальности `(service, version)`.
* Пагинация истории: `?limit=` / `?offset=`.
* Логирование через `twisted.logger`.
* E2E-тесты (treq) + unit-тесты для валидации.
