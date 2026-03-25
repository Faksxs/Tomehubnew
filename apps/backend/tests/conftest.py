import pytest
from unittest.mock import MagicMock

@pytest.fixture
def test_uid():
    """Default Firebase UID for tests."""
    return "test_user_uid_123"

@pytest.fixture
def auth_headers(test_uid):
    """Headers mimicking an authenticated request."""
    return {
        "Authorization": "Bearer fake-token-for-testing",
        "X-Firebase-UID": test_uid
    }

@pytest.fixture
def mock_db(monkeypatch):
    """Provides a mocked database connection fixture."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Mock the common 'get_database_connection' from db_manager
    monkeypatch.setattr("infrastructure.db_manager.get_pool_connection", lambda: mock_conn)
    monkeypatch.setattr("infrastructure.db_manager.get_database_connection", lambda: mock_conn)
    
    return mock_conn, mock_cursor

@pytest.fixture
def anyio_backend():
    """Enable anyio for async tests if needed."""
    return "asyncio"
