import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from supabase import create_client, Client

_found = find_dotenv(usecwd=True)
if _found:
    load_dotenv(_found)
else:
    load_dotenv(Path.home() / ".config" / "taskcli" / ".env")


@lru_cache(maxsize=1)
def client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL and SUPABASE_KEY must be set (see .env.example)")
    return create_client(url, key)
