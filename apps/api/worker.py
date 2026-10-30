"""G3 data-only import queue. Business job execution still belongs to G4."""
import time
from sqlalchemy import text
from goodmcp.database import Database
from goodmcp.version import REVISION
from goodmcp.import_worker import process_one

database = Database(pool_size=1)
while True:
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION
    try:
        worked = process_one(database)
    except Exception:
        # DB outage / membership loss must not print credentials or uploaded content.
        worked = False
    time.sleep(0.2 if worked else 1)
