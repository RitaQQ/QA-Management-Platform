"""
Shared pytest fixtures for backend tests.

Provides a reusable database engine fixture that all test modules
can import via standard pytest fixture injection.
"""
import pytest
from sqlalchemy import create_engine

from database.config import DATABASE_URL


@pytest.fixture(scope='session')
def db_engine():
    """Create a SQLAlchemy engine connected to the development database.

    Scoped to the session so the connection pool is reused across all tests.
    """
    engine = create_engine(DATABASE_URL)
    yield engine
    engine.dispose()
