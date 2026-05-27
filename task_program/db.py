import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from surrealdb import Surreal

_found = find_dotenv(usecwd=True)
if _found:
    load_dotenv(_found)
else:
    load_dotenv(Path.home() / ".config" / "taskcli" / ".env")


@lru_cache(maxsize=1)
def client() -> Surreal:
    url = os.environ.get("SURREALDB_URL")
    user = os.environ.get("SURREALDB_USER")
    password = os.environ.get("SURREALDB_PASS")
    namespace = os.environ.get("SURREALDB_NS", "main")
    database = os.environ.get("SURREALDB_DB", "main")
    if not url or not user or not password:
        sys.exit(
            "SURREALDB_URL, SURREALDB_USER and SURREALDB_PASS must be set "
            "(see .env.example)"
        )
    db = Surreal(url)
    db.signin({"username": user, "password": password})  # root credentials
    db.use(namespace, database)
    return db
