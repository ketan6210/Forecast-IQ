from alembic import context
from sqlalchemy import create_engine

from backend.app.config import settings
from backend.app.db.models import Base

config = context.config


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError(
        "These adoption migrations inspect existing tables; use an online connection."
    )
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        migrate(connection)
