![CI/CD Status](https://github.com/Vovchik777/commentBot/actions/workflows/deploy.yml/badge.svg)

# Telegram Comment Bot

Автоматизатор комментариев для Telegram-каналов и групп: следит за новыми и пересланными постами, публикует заранее заготовленные шаблоны, умеет откладывать комментарии по расписанию, ведёт многоуровневую систему прав и логирует активность в отдельный чат.

## Возможности

- **Авто-комментинг** под новые и пересланные посты (включая альбомы).
- **Ротация шаблонов** с `Faker`-переменными (`{{name}}`, `{{address}}`, `{{phone_number}}`, `{{company}}`).
- **Отложенные комментарии** на конкретную дату + веб-календарь для выбора дня.
- **Банворды** — regex-шаблоны с авто-ответом на сообщения нарушителей.
- **5 уровней прав**: `BASE` → `MODER` → `ADMIN` → `DEV` → `LOGGER`.
- **Логирование** сообщений в админ-чат с автоочисткой записей старше 24 часов.
- **Веб-интерфейс** для обратной связи и планирования.

## Стек

`Python 3.10+` · `Flask 3.0` · `SQLite (WAL)` · `Faker` · `requests` · `pytz` · `pytest` · `Ruff` · `uWSGI (alwaysdata)`

## Команды бота

| Команда | Описание | Мин. права |
| --- | --- | --- |
| `/help` | Справка по командам | `BASE` |
| `/register` | Регистрация в группе (первый вошедший получает `DEV`) | `BASE` |
| `/unregister` | Удалить себя из базы группы | `BASE` |
| `/get_banwords` | Список запрещённых слов группы | `BASE` |
| `/admin_msg` | Ссылка на форму сообщения админу | `BASE` |
| `/get_users_list` | Список пользователей группы с правами | `BASE` |
| `/comment_list` | Список текстовых, фото- и отложенных комментариев | `BASE` |
| `/add_comment [text\|photo] <текст>` | Добавить шаблон комментария | `MODER` |
| `/delete_comment [text\|photo\|scheduled] <номер>` | Удалить комментарий по номеру из `/comment_list` | `MODER` |
| `/set_permission <@username> <уровень>` | Изменить права пользователя | `ADMIN` |
| `/set_schedule_comment <ГГГГ-ММ-ДД> <текст>` | Запланировать комментарий (без аргументов — кнопка-календарь) | `DEV` |
| `/get_user_info [chat_id \| username]` | Информация о пользователе или чате | `DEV` |
| `/answer <текст>` | Ответ на сообщение из лог-чата | `LOGGER` |

> `/answer` работает только в лог-чате: ответом на залогированное сообщение бот доставляет текст в исходный чат.

### Плейсхолдеры шаблонов

При отправке подставляются случайные значения, в базе хранится сам шаблон:

| Плейсхолдер | Значение |
| --- | --- |
| `{{name}}` | ФИО |
| `{{address}}` | Адрес |
| `{{phone_number}}` | Телефон |
| `{{company}}` | Название компании |

Неизвестные плейсхолдеры остаются в тексте как есть.

## Структура проекта

```
src/
  main.py                 # Flask: роуты, вебхук, basic-auth админки
  config.py               # Config из переменных окружения (.env)
  bot/
    core.py               # TelegramBot: Telegram API, альбомы, реакции, рассылка
    handlers/commands.py  # MessageHandler: разбор и обработка команд
    services/            # CommentsManager, MessageLogsManager
    utils/permissions.py  # декоратор @required_permission
  database/
    repository.py         # DataBaseManager: SQL, TTL-воркер, кэш банвордов
    migrations.py         # самописные миграции схемы
    models.py             # User, Comment, Banword, PermissionLevel, CommentTypes
  shared/                 # logger, time_utils (Europe/Moscow)
  web/templates/          # date_pick.html, admin_msg.html
tests/                    # pytest: database + services + handlers
passenger_wsgi.py         # точка входа для alwaysdata (WSGI)
```

## Конфигурация

Создай `.env` в корне проекта. Обязательные переменные проверяются при старте (`config.validate()`).

| Переменная | Обяз. | По умолчанию | Назначение |
| --- | :---: | --- | --- |
| `BOT_TOKEN` | да | — | Токен бота от [@BotFather](https://t.me/BotFather) |
| `LOGGER_CHAT_ID` | да | — | `chat_id` чата для логов и уведомлений |
| `WEBHOOK_SECRET` | нет | `default_secret` | Секрет вебхука (`X-Telegram-Bot-Api-Secret-Token`) |
| `BASE_URL` | нет | `https://alicerasp.alwaysdata.net/tgbot` | Базовый URL для вебхука и кнопок |
| `DB_FILE` | нет | `storage/users.db` | Путь к файлу SQLite |
| `ADMIN_USER` | нет | `admin` | Логин basic-auth веб-панели |
| `ADMIN_PASS` | нет | `secure_pass` | Пароль basic-auth веб-панели |
| `IGNORING_CHAT_IDS` | нет | — | `chat_id` через запятую, где бот не работает |

```ini
BOT_TOKEN=123456:ABC...
LOGGER_CHAT_ID=-1001234567890
WEBHOOK_SECRET=change_me
BASE_URL=https://example.alwaysdata.net/tgbot
DB_FILE=storage/users.db
ADMIN_USER=admin
ADMIN_PASS=secure_pass
```

## Запуск

```bash
git clone https://github.com/Vovchik777/commentBot.git
cd commentBot
python -m venv venv

# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
# создать .env и заполнить BOT_TOKEN и LOGGER_CHAT_ID
python -m src.main     # http://localhost:8000
```

Для работы через вебхук укажи публичный `BASE_URL` и вызови `GET /tgbot/setup` — он зарегистрирует вебхук и `secret_token` в Telegram.

## HTTP-эндпоинты

| Метод | Путь | Доступ | Назначение |
| --- | --- | --- | --- |
| `POST` | `/tgbot/webhook` | `X-Telegram-Bot-Api-Secret-Token` | Приём апдейтов от Telegram |
| `GET` | `/tgbot/setup` | basic-auth | Установить вебхук |
| `GET` | `/tgbot/status` | basic-auth | Статус вебхука (`getWebhookInfo`) |
| `GET` | `/tgbot/health` | открыт | Health-check |
| `GET` | `/tgbot/date_picker` | открыт | Веб-календарь для планирования |
| `GET`/`POST` | `/tgbot/admin_msg` | открыт | Форма обратной связи админу |
| `GET` | `/` | открыт | Информация о сервисе |

## Тесты

`pytest` не входит в `requirements.txt` — установи отдельно (или возьми `requirements-dev.txt`):

```bash
pip install pytest
python -m pytest -q
```

## Линт и форматирование

Линт и форматтер — **Ruff** (конфиг в `ruff.toml`). Зависимости разработки собраны в `requirements-dev.txt`:

```bash
pip install -r requirements-dev.txt
ruff check . --fix      # линт (+ автофикс)
ruff format .           # форматирование (или --check без изменений)

pre-commit install      # хук: Ruff авто-фиксит перед коммитом
pre-commit run --all-files
```

## Деплой

Прод — **alwaysdata**, сайт держит git-чекаут; деплой = `git pull --ff-only` без перезаписи серверной БД.

Автодеплой через GitHub Actions (`.github/workflows/deploy.yml`) при push в `main`:

1. **test** — Python 3.12, установка зависимостей и `pytest`;
2. **lint** — Ruff (`check` + `format --check`), **advisory**: джоб не блокирует деплой (`continue-on-error`);
3. **deploy** — SSH на сервер, `git pull --ff-only` + `pip install`, затем рестарт сайта через alwaysdata API.

> Не заливать `storage/users.db` — перезапись базы стирает пользователей, комментарии и права без предупреждения.
