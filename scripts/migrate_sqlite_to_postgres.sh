#!/bin/bash
#
# Migrate data from SQLite to PostgreSQL
#
# Usage:
#   1. Make sure PostgreSQL is running (docker compose up db -d)
#   2. Set DATABASE_URL in .env to your PostgreSQL connection string
#   3. Run: bash scripts/migrate_sqlite_to_postgres.sh
#
# The script will:
#   - Dump all data from SQLite to a JSON fixture
#   - Run migrations on PostgreSQL
#   - Load the fixture into PostgreSQL
#
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DUMP_FILE="$PROJECT_DIR/data_dump.json"

cd "$PROJECT_DIR"

# Check that DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL is not set."
    echo "Set it in .env or export it, e.g.:"
    echo "  export DATABASE_URL=postgres://tapawingo:password@localhost:5432/tapawingohike"
    exit 1
fi

echo "=== Step 1: Dump data from SQLite ==="
# Temporarily override DATABASE_URL so dumpdata reads from SQLite
DATABASE_URL="" python manage.py dumpdata \
    --natural-foreign \
    --natural-primary \
    --exclude=contenttypes \
    --exclude=auth.permission \
    --exclude=admin.logentry \
    --exclude=sessions.session \
    --indent=2 \
    -o "$DUMP_FILE"

echo "  Dumped to $DUMP_FILE ($(wc -c < "$DUMP_FILE") bytes)"

echo ""
echo "=== Step 2: Run migrations on PostgreSQL ==="
python manage.py migrate --noinput

echo ""
echo "=== Step 3: Load data into PostgreSQL ==="
python manage.py loaddata "$DUMP_FILE"

echo ""
echo "=== Done! ==="
echo "Data has been migrated from SQLite to PostgreSQL."
echo "You can remove $DUMP_FILE if everything looks good."
echo ""
echo "Verify by running:"
echo "  python manage.py shell -c \"from server.apps.dashboard.models import *; print(f'Teams: {Team.objects.count()}, Routes: {Route.objects.count()}, RouteParts: {RoutePart.objects.count()}')\""
