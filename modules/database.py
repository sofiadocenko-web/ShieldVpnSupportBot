import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import aiosqlite


logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    pass


class DatabaseManager:
    def __init__(
        self,
        db_path: str,
        max_connections: int = 5,
        timeout: float = 10.0
    ) -> None:
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool: list[aiosqlite.Connection] = []
        self._semaphore: asyncio.Semaphore | None = None
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        async with self._lock:
            if self._initialized:
                return
            
            self._semaphore = asyncio.Semaphore(self.max_connections)
            
            async with self._get_connection() as conn:
                await conn.execute('PRAGMA journal_mode=WAL')
                await conn.execute('PRAGMA foreign_keys=ON')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        topic_id INTEGER NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_topic_id
                    ON users (topic_id)
                ''')
                
                await conn.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_users_timestamp
                    AFTER UPDATE ON users
                    BEGIN
                        UPDATE users SET updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = NEW.user_id;
                    END
                ''')
                
                await conn.commit()
            
            self._initialized = True
            logger.info("База данных инициализирована")
    
    @asynccontextmanager
    async def _get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        if self._semaphore is None:
            raise DatabaseError("DatabaseManager не инициализирован")
        
        await self._semaphore.acquire()
        conn = None
        
        try:
            conn = await asyncio.wait_for(
                aiosqlite.connect(self.db_path),
                timeout=self.timeout
            )
            conn.row_factory = aiosqlite.Row
            yield conn
        finally:
            if conn:
                await conn.close()
            self._semaphore.release()
    
    async def get_user_topic(self, user_id: int) -> Optional[int]:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError(f"Некорректный user_id: {user_id}")
        
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT topic_id FROM users WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else None
        except asyncio.TimeoutError:
            logger.error(f"Таймаут получения топика для user_id={user_id}")
            raise DatabaseError("Таймаут операции БД")
        except Exception as e:
            logger.error(f"Ошибка получения топика для user_id={user_id}: {e}")
            raise DatabaseError(f"Ошибка БД: {e}")
    
    async def create_user_topic(self, user_id: int, topic_id: int) -> None:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError(f"Некорректный user_id: {user_id}")
        if not isinstance(topic_id, int) or topic_id <= 0:
            raise ValueError(f"Некорректный topic_id: {topic_id}")
        
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO users (user_id, topic_id) VALUES (?, ?)",
                    (user_id, topic_id)
                )
                await conn.commit()
                logger.info(f"Создан топик {topic_id} для user_id={user_id}")
        except asyncio.TimeoutError:
            logger.error(f"Таймаут создания топика для user_id={user_id}")
            raise DatabaseError("Таймаут операции БД")
        except Exception as e:
            logger.error(f"Ошибка создания топика для user_id={user_id}: {e}")
            raise DatabaseError(f"Ошибка БД: {e}")
    
    async def get_user_by_topic(self, topic_id: int) -> Optional[int]:
        if not isinstance(topic_id, int) or topic_id <= 0:
            raise ValueError(f"Некорректный topic_id: {topic_id}")
        
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT user_id FROM users WHERE topic_id = ?",
                    (topic_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else None
        except asyncio.TimeoutError:
            logger.error(f"Таймаут поиска пользователя по topic_id={topic_id}")
            raise DatabaseError("Таймаут операции БД")
        except Exception as e:
            logger.error(f"Ошибка поиска пользователя по topic_id={topic_id}: {e}")
            raise DatabaseError(f"Ошибка БД: {e}")
    
    async def delete_user_topic(self, user_id: int) -> bool:
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError(f"Некорректный user_id: {user_id}")
        
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM users WHERE user_id = ?",
                    (user_id,)
                )
                await conn.commit()
                deleted = cursor.rowcount > 0
                
                if deleted:
                    logger.info(f"Удален топик для user_id={user_id}")
                
                return deleted
        except asyncio.TimeoutError:
            logger.error(f"Таймаут удаления топика для user_id={user_id}")
            raise DatabaseError("Таймаут операции БД")
        except Exception as e:
            logger.error(f"Ошибка удаления топика для user_id={user_id}: {e}")
            raise DatabaseError(f"Ошибка БД: {e}")
    
    async def delete_topic(self, topic_id: int) -> bool:
        """Удалить все привязки к топику"""
        if not isinstance(topic_id, int) or topic_id <= 0:
            raise ValueError(f"Некорректный topic_id: {topic_id}")
        
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM users WHERE topic_id = ?",
                    (topic_id,)
                )
                await conn.commit()
                deleted = cursor.rowcount > 0
                
                if deleted:
                    logger.info(f"Удалены привязки к топику {topic_id}")
                
                return deleted
        except asyncio.TimeoutError:
            logger.error(f"Таймаут удаления топика {topic_id}")
            raise DatabaseError("Таймаут операции БД")
        except Exception as e:
            logger.error(f"Ошибка удаления топика {topic_id}: {e}")
            raise DatabaseError(f"Ошибка БД: {e}")
    
    async def close(self) -> None:
        async with self._lock:
            for conn in self._pool:
                await conn.close()
            self._pool.clear()
            self._initialized = False
            logger.info("База данных закрыта")