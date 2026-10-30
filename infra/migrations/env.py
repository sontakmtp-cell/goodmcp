from alembic import context
from sqlalchemy import create_engine
from goodmcp.config import database_url

engine = create_engine(database_url("migrator"), hide_parameters=True)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
