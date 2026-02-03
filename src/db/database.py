"""
Async SQLite Database Connection Manager

Provides connection pooling and schema initialization for the LoL AI Coach database.
"""

import os
from pathlib import Path
from typing import Optional, Any

import aiosqlite

from ..logging_config import get_logger

logger = get_logger(__name__)

# Default database path
DEFAULT_DB_PATH = Path(os.getenv("COACH_DB_PATH", "./data/lol_coach.db"))

# Schema file location (relative to this file)
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Database:
    """
    Async SQLite database connection manager.

    Usage:
        db = Database()
        await db.connect()
        try:
            row = await db.fetch_one("SELECT * FROM players WHERE id = ?", (1,))
        finally:
            await db.close()

    Or use the singleton:
        db = await get_database()
        row = await db.fetch_one(...)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Initialize database connection and schema."""
        if self._connection is not None:
            return

        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Connecting to database at {self.db_path}")

        self._connection = await aiosqlite.connect(self.db_path)

        # Enable foreign keys
        await self._connection.execute("PRAGMA foreign_keys = ON")

        # Use WAL mode for better concurrency
        await self._connection.execute("PRAGMA journal_mode = WAL")

        # Return rows as dictionaries
        self._connection.row_factory = aiosqlite.Row

        # Initialize schema
        await self._init_schema()

        logger.info("Database connection established")

    async def close(self) -> None:
        """Close database connection."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    async def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        if not SCHEMA_PATH.exists():
            logger.error(f"Schema file not found at {SCHEMA_PATH}")
            raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

        # Execute schema (handles multiple statements)
        await self._connection.executescript(schema_sql)
        await self._connection.commit()

        logger.info("Database schema initialized")

    async def execute(
        self,
        query: str,
        params: tuple = ()
    ) -> aiosqlite.Cursor:
        """
        Execute a query with parameters.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor for the executed query
        """
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        cursor = await self._connection.execute(query, params)
        await self._connection.commit()
        return cursor

    async def execute_many(
        self,
        query: str,
        params_list: list[tuple]
    ) -> None:
        """
        Execute a query with multiple parameter sets.

        Args:
            query: SQL query string
            params_list: List of parameter tuples
        """
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        await self._connection.executemany(query, params_list)
        await self._connection.commit()

    async def fetch_one(
        self,
        query: str,
        params: tuple = ()
    ) -> Optional[dict[str, Any]]:
        """
        Fetch a single row as a dictionary.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Row as dict or None if not found
        """
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        cursor = await self._connection.execute(query, params)
        row = await cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    async def fetch_all(
        self,
        query: str,
        params: tuple = ()
    ) -> list[dict[str, Any]]:
        """
        Fetch all rows as a list of dictionaries.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows as dicts
        """
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        cursor = await self._connection.execute(query, params)
        rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def insert(
        self,
        query: str,
        params: tuple = ()
    ) -> int:
        """
        Execute an INSERT and return the last row ID.

        Args:
            query: INSERT query string
            params: Query parameters

        Returns:
            ID of the inserted row
        """
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        cursor = await self._connection.execute(query, params)
        await self._connection.commit()

        return cursor.lastrowid

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._connection is not None


# Singleton instance
_db: Optional[Database] = None


async def get_database(db_path: Optional[Path] = None) -> Database:
    """
    Get the singleton database instance.

    Creates and connects if not already connected.

    Args:
        db_path: Optional custom database path (only used on first call)

    Returns:
        Connected Database instance
    """
    global _db

    if _db is None:
        _db = Database(db_path)
        await _db.connect()

    return _db


async def close_database() -> None:
    """Close the singleton database connection."""
    global _db

    if _db is not None:
        await _db.close()
        _db = None
