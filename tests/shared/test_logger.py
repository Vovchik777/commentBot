import logging

from src.shared.logger import MaskSecretsFilter, mask_secrets

# Фейковый токен: реальный сюда попадать не должен (репозиторий публичный).
TOKEN = "123456789:FAKE_Token-ForTestsOnly"
SECRET_PART = "FAKE_Token-ForTestsOnly"
URL = f"400 Client Error for url: https://api.telegram.org/bot{TOKEN}/sendMessage"


def test_mask_secrets_hides_bot_token():
    masked = mask_secrets(URL)

    assert TOKEN not in masked
    assert SECRET_PART not in masked
    assert masked.endswith("/sendMessage")
    assert "bot<hidden>" in masked


def test_mask_secrets_keeps_plain_text():
    assert mask_secrets("ничего секретного") == "ничего секретного"


def test_mask_secrets_filter_cleans_record():
    record = logging.LogRecord(
        "commentBot.bot", logging.ERROR, __file__, 1, "Ошибка: %s", (URL,), None
    )

    MaskSecretsFilter().filter(record)

    message = record.getMessage()
    assert TOKEN not in message
    assert message.startswith("Ошибка: ")
