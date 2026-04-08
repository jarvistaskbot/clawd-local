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


def test_default_project_is_general():
    project = memory.get_active_project(111)
    assert project == "general"


def test_create_project_session():
    ps = memory.get_or_create_project_session(111, "arbitrage")
    assert ps["name"] == "arbitrage"
    assert ps["claude_session_id"] is None
    assert ps["id"] > 0


def test_switch_project_session():
    memory.set_active_project(111, "arbitrage")
    assert memory.get_active_project(111) == "arbitrage"

    memory.set_active_project(111, "tls")
    assert memory.get_active_project(111) == "tls"

    # Switch back
    memory.set_active_project(111, "arbitrage")
    assert memory.get_active_project(111) == "arbitrage"


def test_list_project_sessions():
    memory.get_or_create_project_session(111, "arbitrage")
    memory.get_or_create_project_session(111, "tls")
    memory.get_or_create_project_session(111, "general")

    sessions = memory.list_project_sessions(111)
    names = [s["name"] for s in sessions]
    assert "arbitrage" in names
    assert "tls" in names
    assert "general" in names


def test_delete_project_session():
    memory.get_or_create_project_session(111, "temp_project")
    assert memory.delete_project_session(111, "temp_project") is True
    # Should not appear in list
    sessions = memory.list_project_sessions(111)
    names = [s["name"] for s in sessions]
    assert "temp_project" not in names


def test_delete_nonexistent_returns_false():
    assert memory.delete_project_session(111, "nope") is False


def test_project_history_isolation():
    """History from 'arbitrage' should not be visible in 'tls'."""
    user_id = 222

    # Create project sessions
    memory.get_or_create_project_session(user_id, "arbitrage")
    memory.get_or_create_project_session(user_id, "tls")

    # Get chat sessions
    arb_session = memory.get_or_create_project_chat_session(user_id, "arbitrage")
    tls_session = memory.get_or_create_project_chat_session(user_id, "tls")

    # They should be different sessions
    assert arb_session != tls_session

    # Add messages to arbitrage
    memory.add_message(arb_session, "user", "arbitrage message 1")
    memory.add_message(arb_session, "assistant", "arbitrage response 1")

    # Add messages to tls
    memory.add_message(tls_session, "user", "tls message 1")

    # Check isolation
    arb_history = memory.get_history(arb_session)
    tls_history = memory.get_history(tls_session)

    assert len(arb_history) == 2
    assert len(tls_history) == 1
    assert arb_history[0]["content"] == "arbitrage message 1"
    assert tls_history[0]["content"] == "tls message 1"


def test_project_chat_session_persistence():
    """Same project should return the same chat session on repeated calls."""
    user_id = 333
    s1 = memory.get_or_create_project_chat_session(user_id, "myproject")
    s2 = memory.get_or_create_project_chat_session(user_id, "myproject")
    assert s1 == s2


def test_claude_session_id_storage():
    user_id = 444
    memory.get_or_create_project_session(user_id, "test_proj")

    # Initially None
    assert memory.get_project_claude_session_id(user_id, "test_proj") is None

    # Store session ID
    memory.update_project_claude_session(user_id, "test_proj", "abc-123-def")
    assert memory.get_project_claude_session_id(user_id, "test_proj") == "abc-123-def"

    # Update it
    memory.update_project_claude_session(user_id, "test_proj", "xyz-789")
    assert memory.get_project_claude_session_id(user_id, "test_proj") == "xyz-789"


def test_reset_project_session():
    user_id = 555
    memory.get_or_create_project_session(user_id, "resettable")
    memory.update_project_claude_session(user_id, "resettable", "old-session-id")

    s1 = memory.get_or_create_project_chat_session(user_id, "resettable")
    memory.add_message(s1, "user", "old message")

    # Reset
    s2 = memory.reset_project_session(user_id, "resettable")
    assert s2 != s1

    # New session should have no user messages
    history = memory.get_history(s2)
    assert len(history) == 0

    # Claude session should be cleared
    assert memory.get_project_claude_session_id(user_id, "resettable") is None

    # New chat session should point to the reset one
    s3 = memory.get_or_create_project_chat_session(user_id, "resettable")
    assert s3 == s2


def test_list_sessions_shows_active():
    user_id = 666
    memory.get_or_create_project_session(user_id, "proj_a")
    memory.get_or_create_project_session(user_id, "proj_b")
    memory.set_active_project(user_id, "proj_b")

    sessions = memory.list_project_sessions(user_id)
    active = [s for s in sessions if s["is_active"]]
    assert len(active) == 1
    assert active[0]["name"] == "proj_b"
