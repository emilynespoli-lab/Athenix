from alembic import context

from athenix.config import Settings
from athenix.db import Base, database

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    settings = Settings()
    settings.prepare()
    engine, _ = database(settings.database_url)
    with engine.begin() as connection:
        run(connection)
    engine.dispose()
