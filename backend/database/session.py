"""
SQLAlchemy session factory.

Provides a centralized engine and session factory for all database access.
Use ``SessionLocal()`` for manual session management, or ``get_db()``
as a generator-based context helper.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.config import DATABASE_URL

_engine_kwargs = {'pool_pre_ping': True}
if not DATABASE_URL.startswith('sqlite'):
    _engine_kwargs['pool_size'] = 10
engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """Yield a database session and ensure it is closed afterwards.

    Usage::

        for db in get_db():
            db.query(...)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
