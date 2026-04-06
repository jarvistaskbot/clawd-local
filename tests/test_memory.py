import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import memory


def setup_function():
    """Use a temp database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    config.DB_PATH = path
    memory.DB_PATH = path
    memory.init_db()


def teardown_function():
    try:
        os.unlink(config.DB_PATH)
    except OSError:
        pass


def test_session_creation():
    session_id = memory.get_or_create_session(111)
    assert isinstance(session_id, int)
    assert session_id > 0


def test_same_user_gets_same_session():
    s1 = memory.get_or_create_session(222)
    s2 = memory.get_or_create_session(222)
    assert s1 == s2


def test_message_storage_and_retrieval():
    session_id = memory.get_or_create_session(333)
    memory.add_message(session_id, "user", "hello")
    memory.add_message(session_id, "assistant", "hi there")
    history = memory.get_history(session_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "hi there"


def test_history_limit():
    session_id = memory.get_or_create_session(444)
    for i in range(30):
        memory.add_message(session_id, "user", f"msg {i}")
    history = memory.get_history(session_id, limit=10)
    assert len(history) == 10
    # Should be the last 10 messages
    assert history[0]["content"] == "msg 20"
    assert history[-1]["content"] == "msg 29"


def test_session_reset():
    s1 = memory.get_or_create_session(555)
    memory.add_message(s1, "user", "old message")
    s2 = memory.reset_session(555)
    assert s2 != s1
    # New session should have no messages
    history = memory.get_history(s2)
    assert len(history) == 0
    # get_or_create should now return the new session
    s3 = memory.get_or_create_session(555)
    assert s3 == s2


def test_clear_last_messages():
    session_id = memory.get_or_create_session(777)
    for i in range(10):
        memory.add_message(session_id, "user", f"msg {i}")
    deleted = memory.clear_last_messages(session_id, 3)
    assert deleted == 3
    history = memory.get_history(session_id)
    assert len(history) == 7
    # Last remaining message should be msg 6
    assert history[-1]["content"] == "msg 6"


def test_clear_more_than_exists():
    session_id = memory.get_or_create_session(888)
    memory.add_message(session_id, "user", "only one")
    deleted = memory.clear_last_messages(session_id, 100)
    assert deleted == 1
    history = memory.get_history(session_id)
    assert len(history) == 0


def test_stats():
    user_id = 666
    s1 = memory.get_or_create_session(user_id)
    memory.add_message(s1, "user", "msg1")
    memory.add_message(s1, "assistant", "resp1")
    memory.reset_session(user_id)
    stats = memory.get_stats(user_id)
    assert stats["session_count"] == 2
    assert stats["total_messages"] == 2
