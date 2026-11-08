import hmac
from functools import wraps
from urllib.parse import urlparse

from flask import Response, current_app, request

from src.config import Config

# Запасной конфиг для случаев, когда приложение ещё не положило свой в
# app.extensions["config"] (например, в тестах блюпринта).
config = Config()


def get_config() -> Config:
    """Конфиг приложения: сначала из extension, потом модульный запасной."""
    try:
        app_config = current_app.extensions.get("config")
    except RuntimeError:
        app_config = None
    return app_config or config


def _unauthorized():
    return Response("Доступ запрещён", 401, {"WWW-Authenticate": 'Basic realm="Admin Area"'})


def _forbidden():
    return Response("Доступ запрещён: неверный логин или пароль", 403)


def is_admin_request() -> bool:
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return False

    cfg = get_config()
    username_ok = hmac.compare_digest(auth.username, cfg.ADMIN_USER or "")
    password_ok = hmac.compare_digest(auth.password, cfg.ADMIN_PASS or "")
    return username_ok and password_ok


def is_safe_origin() -> bool:
    """Грубая защита от CSRF для POST-форм админки.

    Basic-auth браузер подставляет сам, поэтому чужой сайт мог бы отправить
    форму от имени админа. Если браузер прислал Origin/Referer — сверяем его
    с текущим хостом и BASE_URL. Запросы без заголовков (curl, тесты) пускаем.
    """
    source = request.headers.get("Origin") or request.headers.get("Referer")
    if not source:
        return True

    parsed = urlparse(source)
    source_origin = f"{parsed.scheme}://{parsed.netloc}"

    allowed = {request.host_url.rstrip("/")}
    base_url = get_config().BASE_URL
    if base_url:
        allowed.add(base_url.rstrip("/"))

    return source_origin in allowed


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not request.authorization:
            return _unauthorized()
        if not is_admin_request():
            return _forbidden()
        return f(*args, **kwargs)

    return wrapper
