"""
Общие зависимости FastAPI (dependency injection).
Импортируются из main.py и всех роутеров.
Переопределяются в тестах через app.dependency_overrides[get_db].
"""
from app.database import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db() -> AsyncSession:
    """Async сессия БД на время запроса."""
    async with AsyncSessionLocal() as db:
        yield db