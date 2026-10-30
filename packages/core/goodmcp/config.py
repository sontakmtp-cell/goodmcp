from pathlib import Path
import os

from sqlalchemy.engine import URL


def secret(name: str) -> str:
    value = (Path(os.environ.get("HUB_SECRETS_DIR", "/run/secrets")) / name).read_text(encoding="utf-8").strip()
    if len(value) < 16:
        raise RuntimeError("Local secret is missing or too short")
    return value


def database_url(role: str = "runtime") -> URL:
    names = {"runtime": ("hub_runtime", "runtime_password"),
             "migrator": ("hub_migrator", "migrator_password"),
             "admin": ("postgres", "admin_password")}
    user, filename = names[role]
    return URL.create("postgresql+psycopg", username=user, password=secret(filename),
                      host=os.environ.get("HUB_DB_HOST", "postgres"),
                      database=os.environ.get("HUB_DB_NAME", "goodmcp"))
