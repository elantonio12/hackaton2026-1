import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


async def sync_schema():
    """Create missing tables and add missing columns to existing tables.

    This replaces Alembic for the hackathon — on each startup the ORM
    metadata is compared against the live database and any new tables or
    columns are added automatically via CREATE TABLE / ALTER TABLE.
    """
    from app.db.models import Base

    async with engine.begin() as conn:
        # 1. Create any brand-new tables
        await conn.run_sync(Base.metadata.create_all)

        # 2. Add missing columns to existing tables
        def _add_missing_columns(sync_conn):
            insp = inspect(sync_conn)
            existing_tables = set(insp.get_table_names())

            for table_name, table in Base.metadata.tables.items():
                if table_name not in existing_tables:
                    continue
                existing_cols = {c["name"] for c in insp.get_columns(table_name)}
                for column in table.columns:
                    if column.name in existing_cols:
                        continue
                    col_type = column.type.compile(sync_conn.dialect)
                    parts = [f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}"]
                    if column.default is not None:
                        val = column.default.arg
                        if isinstance(val, bool):
                            parts.append(f" DEFAULT {'true' if val else 'false'}")
                        elif isinstance(val, str):
                            parts.append(f" DEFAULT '{val}'")
                        else:
                            parts.append(f" DEFAULT {val}")
                    elif column.nullable:
                        parts.append(" DEFAULT NULL")
                    else:
                        parts.append(" DEFAULT NULL")
                    stmt = "".join(parts)
                    sync_conn.execute(text(stmt))
                    logger.info("[Schema] Added column %s.%s (%s)", table_name, column.name, col_type)

        await conn.run_sync(_add_missing_columns)
