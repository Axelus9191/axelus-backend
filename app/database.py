from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# Файл базы данных будет создан автоматически
DATABASE_URL = "sqlite+aiosqlite:///./axelus.db"

# Движок для работы с БД
engine = create_async_engine(DATABASE_URL, echo=False)

# Фабрика сессий (одна сессия = один запрос)
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Базовый класс для моделей
Base = declarative_base()


# Функция получения сессии для эндпоинтов
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session