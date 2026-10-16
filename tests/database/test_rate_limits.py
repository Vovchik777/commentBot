import sqlite3
import time

from src.config import Config


config = Config()


def _rows(db_manager, ip):
    conn = sqlite3.connect(db_manager.db_file)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM admin_msg_rate_limits WHERE ip = ?", (ip,)
        ).fetchone()[0]
    finally:
        conn.close()


def test_admin_msg_rate_hit_allows_under_limit(db_manager):
    for _ in range(config.ADMIN_MSG_RATE_LIMIT):
        assert db_manager.admin_msg_rate_hit("1.2.3.4") is False

    assert _rows(db_manager, "1.2.3.4") == config.ADMIN_MSG_RATE_LIMIT


def test_admin_msg_rate_hit_blocks_over_limit(db_manager):
    for _ in range(config.ADMIN_MSG_RATE_LIMIT):
        db_manager.admin_msg_rate_hit("1.2.3.4")

    assert db_manager.admin_msg_rate_hit("1.2.3.4") is True
    assert _rows(db_manager, "1.2.3.4") == config.ADMIN_MSG_RATE_LIMIT


def test_admin_msg_rate_hit_clears_expired(db_manager):
    expired_ts = time.time() - config.ADMIN_MSG_RATE_WINDOW - 1
    conn = sqlite3.connect(db_manager.db_file)
    try:
        for _ in range(config.ADMIN_MSG_RATE_LIMIT):
            conn.execute(
                "INSERT INTO admin_msg_rate_limits (ip, ts, expires_at) VALUES (?, ?, ?)",
                ("1.2.3.4", expired_ts, expired_ts + config.ADMIN_MSG_RATE_WINDOW),
            )
        conn.commit()
    finally:
        conn.close()

    assert db_manager.admin_msg_rate_hit("1.2.3.4") is False
    assert _rows(db_manager, "1.2.3.4") == 1


def test_admin_msg_rate_hit_isolated_per_ip(db_manager):
    for _ in range(config.ADMIN_MSG_RATE_LIMIT):
        db_manager.admin_msg_rate_hit("1.2.3.4")

    assert db_manager.admin_msg_rate_hit("1.2.3.4") is True
    assert db_manager.admin_msg_rate_hit("5.6.7.8") is False
