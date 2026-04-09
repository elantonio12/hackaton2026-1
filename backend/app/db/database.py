import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


async def run_migrations():
    """Run Alembic migrations programmatically (alembic upgrade head)."""
    from alembic import command
    from alembic.config import Config

    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ini_path = os.path.join(backend_dir, "alembic.ini")

    if not os.path.exists(ini_path):
        logger.warning("[DB] alembic.ini not found, falling back to create_all")
        from app.db.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return

    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    async with engine.begin() as conn:
        await conn.run_sync(_do_upgrade, alembic_cfg)

    logger.info("[DB] Alembic migrations applied")


def _do_upgrade(connection, alembic_cfg):
    from alembic import command
    from sqlalchemy import inspect

    alembic_cfg.attributes["connection"] = connection

    # If tables exist but alembic_version doesn't, stamp to initial revision
    # (handles DBs created before Alembic was added)
    insp = inspect(connection)
    tables = set(insp.get_table_names())
    if "users" in tables and "alembic_version" not in tables:
        logger.info("[DB] Existing DB without alembic_version — stamping to 0001")
        command.stamp(alembic_cfg, "0001")

    command.upgrade(alembic_cfg, "head")
