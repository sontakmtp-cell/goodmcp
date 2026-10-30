"""G1 readiness loop only. Job claiming/execution belongs to G4."""
import time
from sqlalchemy import text
from goodmcp.database import Database

database = Database(pool_size=1)
while True:
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001_g1"
    time.sleep(10)
