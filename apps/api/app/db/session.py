
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


settings = get_settings()

if not settings.database_url:
    raise RuntimeError("PFA_DATABASE_URL is not configured.")

# Create one reusable connection pool for the application.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

# Each request or operation gets its own database session.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def get_db():
    """Provide a database session and always close it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
