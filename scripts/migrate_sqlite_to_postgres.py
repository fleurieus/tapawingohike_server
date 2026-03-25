"""
Migrate data from SQLite to PostgreSQL.

Usage:
    1. Make sure PostgreSQL is running (docker compose up db -d)
    2. Run: python scripts/migrate_sqlite_to_postgres.py
       with DATABASE_URL set to the PostgreSQL connection string.

    Or pass it as an argument:
       python scripts/migrate_sqlite_to_postgres.py postgres://tapawingo:password@localhost:5432/tapawingohike
"""
import os
import sys
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DUMP_FILE = PROJECT_DIR / "data_dump.json"
MANAGE = [sys.executable, str(PROJECT_DIR / "manage.py")]


def run(cmd, env=None):
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, cwd=str(PROJECT_DIR), env=merged)
    if result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def main():
    database_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL", "")

    if not database_url or "postgres" not in database_url:
        print("ERROR: Provide a PostgreSQL DATABASE_URL.")
        print("  Either set it as environment variable or pass as argument:")
        print(f"  python {__file__} postgres://tapawingo:password@localhost:5432/tapawingohike")
        sys.exit(1)

    print("=== Step 1: Dump data from SQLite ===")
    # Unset DATABASE_URL so dumpdata reads from SQLite (the default fallback)
    run([
        *MANAGE, "dumpdata",
        "--natural-foreign",
        "--natural-primary",
        "--exclude=contenttypes",
        "--exclude=auth.permission",
        "--exclude=admin.logentry",
        "--exclude=sessions.session",
        "--indent=2",
        "-o", str(DUMP_FILE),
    ], env={"DATABASE_URL": ""})

    size = DUMP_FILE.stat().st_size
    print(f"  Dumped to {DUMP_FILE} ({size:,} bytes)")

    print("\n=== Step 2: Run migrations on PostgreSQL ===")
    run([*MANAGE, "migrate", "--noinput"], env={"DATABASE_URL": database_url})

    print("\n=== Step 3: Load data into PostgreSQL ===")
    run([*MANAGE, "loaddata", str(DUMP_FILE)], env={"DATABASE_URL": database_url})

    print("\n=== Done! ===")
    print(f"Data migrated from SQLite to PostgreSQL.")
    print(f"You can remove {DUMP_FILE} if everything looks good.")
    print(f"\nVerify:")
    print(f"  DATABASE_URL={database_url} python manage.py shell -c \"from server.apps.dashboard.models import *; print(f'Teams: {{Team.objects.count()}}, Routes: {{Route.objects.count()}}')\"\n")


if __name__ == "__main__":
    main()
