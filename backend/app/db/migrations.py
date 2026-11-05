from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config
from sqlalchemy import text

_lock = Lock()


def migrate_database(engine) -> None:
    """Adopt old databases and apply additive revisions using the application's connection."""
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "migrations")
    )
    with _lock, engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(37031422)"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
