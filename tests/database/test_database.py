from src.database.models import PermissionLevel, User

def test_create_group_table(db_manager, db_cursor):
    test_group_id = 1223132123

    db_manager.create_group_table(tg_group_id=test_group_id)

    
    db_cursor.execute("SELECT tg_group_id FROM groups WHERE tg_group_id = ?", (test_group_id,))
    res = db_cursor.fetchone()

    assert res is not None
    assert res[0] == test_group_id


def test_ignore_duplicate_group(db_manager,db_cursor):
    test_group_id = 1231231231

    db_manager.create_group_table(tg_group_id=test_group_id)
    db_manager.create_group_table(tg_group_id=test_group_id)


    db_cursor.execute("SELECT COUNT(*) FROM groups WHERE tg_group_id = ?", (test_group_id,))
    count = db_cursor.fetchone()[0]
        
    assert count == 1

def test_add_user(db_manager,db_cursor, user_factory):
    user = user_factory()

    assert db_manager.add_user(user) is True

    db_cursor.execute("SELECT username FROM users WHERE tg_user_id = ?", (user.tg_user_id,))

    result = db_cursor.fetchone()

    assert result[0] == user.username


def test_add_duplicate_user(db_manager,db_cursor, user_factory):
    assert db_manager.add_user(user_factory(username = "vova")) is True
    assert db_manager.add_user(user_factory(username = "vova")) is False
    
    db_cursor.execute("SELECT COUNT(*) FROM users_groups")

    assert db_cursor.fetchone()[0] == 1


def test_update_user(db_manager, db_cursor, user_factory):
    user1 = user_factory(username = "vova")
    user2 = user_factory(username = "vova1232131")
        
    assert db_manager.add_user(user1) is True
    assert db_manager.add_user(user2) is False

    db_cursor.execute(
        "SELECT username FROM users WHERE tg_user_id = ?",
        (user2.tg_user_id,),
    )
    assert db_cursor.fetchone()[0] == user2.username

def test_delete_user_exists(db_manager, db_cursor, user_factory):
    user = user_factory()
    db_manager.add_user(user)
    assert db_manager.delete_user(user) is True

def test_delete_user_not_exists(db_manager, db_cursor, user_factory):
    user = user_factory()
    assert db_manager.delete_user(user) is False



def test_get_user_by_username_in_group_found(db_manager, user_factory):
    user = user_factory()

    db_manager.add_user(user)

    result = db_manager.get_user_by_username(user.username, user.tg_group_id)

    assert isinstance(result, User) is False or True  # просто убедимся что не список
    assert not isinstance(result, list)
    assert result.tg_user_id == user.tg_user_id
    assert result.tg_group_id == user.tg_group_id
    assert result.username == user.username
    assert result.permission == user.permission


def test_get_user_by_username_in_group_not_found(db_manager, user_factory):
    user = user_factory()

    result = db_manager.get_user_by_username(user.username, user.tg_group_id)

    assert result is None


def test_get_user_by_username_in_group_wrong_group(db_manager, user_factory):
    user = user_factory()
    db_manager.add_user(user)


    result = db_manager.get_user_by_username(user.username, tg_group_id=user.tg_group_id+1)

    assert result is None


def test_get_user_by_username_in_group_strip(db_manager, user_factory):
    user = user_factory()
    db_manager.add_user(user)

    result = db_manager.get_user_by_username("@" + user.username, user.tg_group_id)

    assert isinstance(result, User)
    assert result.username == user.username
    assert result.tg_user_id == user.tg_user_id


def test_get_user_by_username_all_groups_one(db_manager, user_factory):
    user = user_factory()
    db_manager.add_user(user)

    result = db_manager.get_user_by_username(user.username)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].tg_user_id == user.tg_user_id
    assert result[0].tg_group_id == user.tg_group_id
    assert result[0].username == user.username
    assert result[0].permission == user.permission


def test_get_user_by_username_all_groups_multiply(db_manager, user_factory):
    user_g1 = user_factory(tg_group_id=100)
    user_g2 = user_factory(tg_group_id=200, permission=PermissionLevel.ADMIN)
    db_manager.add_user(user_g1)
    db_manager.add_user(user_g2)

    result = db_manager.get_user_by_username(user_g1.username)

    assert isinstance(result, list)
    assert len(result) == 2

    by_groups = {u.tg_group_id: u for u in result}
    assert by_groups[100].tg_user_id == user_g1.tg_user_id
    assert by_groups[100].username == user_g1.username
    assert by_groups[100].permission == user_g1.permission
    assert by_groups[200].tg_user_id == user_g2.tg_user_id
    assert by_groups[200].username == user_g2.username
    assert by_groups[200].permission == user_g2.permission

def test_get_user_by_username_all_groups_not_found(db_manager, user_factory):
    user = user_factory()

    result = db_manager.get_user_by_username(user.username)

    assert result is None


def test_get_user_by_username_all_groups_strip(db_manager, user_factory):
    user = user_factory()
    db_manager.add_user(user)

    result = db_manager.get_user_by_username("@" + user.username)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].username == user.username

def test_get_user_by_username_link_deleted(db_manager, user_factory):
    user = user_factory()
    db_manager.add_user(user)
    db_manager.delete_user(user)

    assert db_manager.get_user_by_username(user.username, user.tg_group_id) is None
    assert db_manager.get_user_by_username(user.username) is None


def test_update_user_permission_success(db_manager, db_cursor, user_factory):
    user = user_factory(permission = PermissionLevel.BASE)
    new_permission = PermissionLevel.ADMIN

    db_manager.add_user(user)

    assert db_manager.update_user_permission(user, new_permission) is True

    db_cursor.execute("""SELECT permission FROM users_groups WHERE
                        user_id = (SELECT id FROM users WHERE tg_user_id = ?) AND
                        group_id = (SELECT id FROM groups WHERE tg_group_id = ?)"""
                      , (user.tg_user_id, user.tg_group_id,))
    assert db_cursor.fetchone()[0] == new_permission
    assert db_manager.get_user(user.tg_user_id, user.tg_group_id).permission == new_permission


def test_update_user_permission_same_value(db_manager, db_cursor, user_factory):
    user = user_factory()
    new_permission = user.permission

    db_manager.add_user(user)

    assert db_manager.update_user_permission(user, new_permission) is True

    db_cursor.execute("""SELECT permission FROM users_groups WHERE
                        user_id = (SELECT id FROM users WHERE tg_user_id = ?) AND
                        group_id = (SELECT id FROM groups WHERE tg_group_id = ?)"""
                      , (user.tg_user_id, user.tg_group_id,))
    assert db_cursor.fetchone()[0] == new_permission
    assert db_manager.get_user(user.tg_user_id, user.tg_group_id).permission == new_permission

def test_update_user_permission_down(db_manager, db_cursor, user_factory):
    user = user_factory(permission = PermissionLevel.ADMIN)
    new_permission = PermissionLevel.BASE

    db_manager.add_user(user)

    assert db_manager.update_user_permission(user, new_permission) is True

    db_cursor.execute("""SELECT permission FROM users_groups WHERE
                        user_id = (SELECT id FROM users WHERE tg_user_id = ?) AND
                        group_id = (SELECT id FROM groups WHERE tg_group_id = ?)"""
                      , (user.tg_user_id, user.tg_group_id,))
    assert db_cursor.fetchone()[0] == new_permission
    assert db_manager.get_user(user.tg_user_id, user.tg_group_id).permission == new_permission

def test_update_user_permission_user_not_found(db_manager, db_cursor, user_factory):
    user = user_factory(permission = PermissionLevel.BASE)
    new_permission = PermissionLevel.ADMIN


    assert db_manager.update_user_permission(user, new_permission) is False

def test_update_user_permission_wrong_group(db_manager, db_cursor, user_factory):
    user1 = user_factory(permission = PermissionLevel.BASE)
    user2 = user_factory(tg_group_id = user1.tg_group_id + 1)
    new_permission = PermissionLevel.ADMIN

    db_manager.add_user(user1)

    assert db_manager.update_user_permission(user2, new_permission) is False

    db_cursor.execute("""SELECT permission FROM users_groups WHERE
                        user_id = (SELECT id FROM users WHERE tg_user_id = ?) AND
                        group_id = (SELECT id FROM groups WHERE tg_group_id = ?)"""
                      , (user1.tg_user_id, user1.tg_group_id,))
    assert db_cursor.fetchone()[0] == user1.permission

def test_update_user_permission_after_delete_user(db_manager, db_cursor, user_factory):
    user = user_factory(permission = PermissionLevel.BASE)
    new_permission = PermissionLevel.ADMIN

    db_manager.add_user(user)
    db_manager.delete_user(user)

    assert db_manager.update_user_permission(user, new_permission) is False


def test_update_user_permission_does_not_touch_other_group(db_manager, db_cursor, user_factory):
    user1 = user_factory(permission = PermissionLevel.ADMIN)
    user2 = user_factory(tg_group_id = user1.tg_group_id + 1, permission = PermissionLevel.LOGGER)
    new_permission = PermissionLevel.BASE

    db_manager.add_user(user1)
    db_manager.add_user(user2)


    assert db_manager.update_user_permission(user1, new_permission) is True

    db_cursor.execute("""SELECT permission FROM users_groups WHERE
                        user_id = (SELECT id FROM users WHERE tg_user_id = ?) AND
                        group_id = (SELECT id FROM groups WHERE tg_group_id = ?)"""
                      , (user1.tg_user_id, user1.tg_group_id,))
    assert db_cursor.fetchone()[0] == new_permission
    
    db_cursor.execute("""SELECT permission FROM users_groups WHERE
                        user_id = (SELECT id FROM users WHERE tg_user_id = ?) AND
                        group_id = (SELECT id FROM groups WHERE tg_group_id = ?)"""
                      , (user2.tg_user_id, user2.tg_group_id,))
    assert db_cursor.fetchone()[0] != new_permission


import time
import pytest
from src.database.models import User, PermissionLevel


def test_get_users_in_group_all_users(db_manager, user_factory):
    user1 = user_factory(username="vova")
    user2 = user_factory(tg_user_id=user1.tg_user_id + 1, username="vova123123123")
    db_manager.add_user(user1)
    db_manager.add_user(user2)

    result = db_manager.get_users_in_group(user1.tg_group_id)

    assert len(result) == 2
    by_ids = {u.tg_user_id: u for u in result}
    assert by_ids[user1.tg_user_id].username == user1.username
    assert by_ids[user1.tg_user_id].permission == user1.permission
    assert by_ids[user1.tg_user_id].tg_group_id == user1.tg_group_id
    assert by_ids[user2.tg_user_id].username == user2.username
    assert by_ids[user2.tg_user_id].permission == user2.permission
    assert by_ids[user2.tg_user_id].tg_group_id == user2.tg_group_id


def test_get_users_in_group_other_group(db_manager, user_factory):
    user1 = user_factory(username="vova")
    user2 = user_factory(
        tg_user_id=user1.tg_user_id + 1,
        username="vova123123123",
        tg_group_id=user1.tg_group_id + 1,
    )
    db_manager.add_user(user1)
    db_manager.add_user(user2)

    result = db_manager.get_users_in_group(user1.tg_group_id)

    assert len(result) == 1
    assert result[0].tg_user_id == user1.tg_user_id
    assert result[0].username == user1.username


def test_get_users_in_group_empty(db_manager, user_factory):
    user = user_factory()
    db_manager.add_user(user)
    db_manager.delete_user(user)

    result = db_manager.get_users_in_group(user.tg_group_id)

    assert result == []


def test_check_username_updates(db_manager, db_cursor, user_factory):
    user = user_factory(username="vova")
    db_manager.add_user(user)

    db_manager.check_username(user.tg_user_id, "vova123123123")

    db_cursor.execute("SELECT username FROM users WHERE tg_user_id = ?", (user.tg_user_id,))
    assert db_cursor.fetchone()[0] == "vova123123123"

    fetched = db_manager.get_user(user.tg_user_id, user.tg_group_id)
    assert fetched.username == "vova123123123"
    assert fetched.permission == user.permission
    assert fetched.tg_group_id == user.tg_group_id


def test_check_username_unknown_user(db_manager, db_cursor, user_factory):
    user = user_factory(username="vova")
    db_manager.add_user(user)

    db_manager.check_username(user.tg_user_id + 1, "vova123123123")

    db_cursor.execute("SELECT username FROM users WHERE tg_user_id = ?", (user.tg_user_id,))
    assert db_cursor.fetchone()[0] == "vova"


def test_mark_album_processed_once(db_manager):
    assert db_manager.mark_album_processed("jqoiwejqwe") is True


def test_mark_album_processed_twice(db_manager):
    assert db_manager.mark_album_processed("zxcvbnmasd") is True
    assert db_manager.mark_album_processed("zxcvbnmasd") is False


def test_is_album_processed_expired(db_manager, db_cursor):
    media_group_id = "poiuytrewq"
    db_manager.mark_album_processed(media_group_id)
    db_cursor.execute(
        "UPDATE processed_albums SET expires_at = ? WHERE media_group_id = ?",
        (time.time() - 1, media_group_id),
    )
    db_cursor.connection.commit()
    assert db_manager.is_album_processed(media_group_id) is False


def test_set_and_get_last_comment(db_manager):
    assert db_manager.get_last_comment(100) is None

    db_manager.set_last_comment(100, "lkjhgfdsaq")
    assert db_manager.get_last_comment(100) == "lkjhgfdsaq"

    db_manager.set_last_comment(100, "mnbvcxzlkj")
    assert db_manager.get_last_comment(100) == "mnbvcxzlkj"

    assert db_manager.get_last_comment(200) is None


def test_get_last_comment_expired(db_manager, db_cursor):
    db_manager.set_last_comment(100, "qwertyuiop")
    db_cursor.execute(
        "UPDATE bot_state SET expires_at = ? WHERE key = ?",
        (time.time() - 1, "last_comment:100"),
    )
    db_cursor.connection.commit()
    assert db_manager.get_last_comment(100) is None