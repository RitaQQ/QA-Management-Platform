"""
Database configuration module.

Centralizes all database and cache connection settings.
Uses environment variables with sensible defaults for local development.
"""
import os

DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'sqlite:///data/qa.db'
)

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
