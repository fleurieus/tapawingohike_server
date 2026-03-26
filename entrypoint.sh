#!/bin/bash
set -e

# Wait for database to be ready (only when using PostgreSQL)
if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q "postgres"; then
    echo "Waiting for PostgreSQL..."
    python -c "
import time, dj_database_url, psycopg2
conf = dj_database_url.parse('$DATABASE_URL')
for i in range(30):
    try:
        psycopg2.connect(dbname=conf['NAME'], user=conf['USER'],
                         password=conf['PASSWORD'], host=conf['HOST'],
                         port=conf['PORT'])
        print('PostgreSQL is ready.')
        break
    except psycopg2.OperationalError:
        print(f'Waiting... ({i+1}/30)')
        time.sleep(1)
else:
    print('ERROR: Could not connect to PostgreSQL after 30 seconds')
    exit(1)
"
fi

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Compressing static files..."
python manage.py compress --force

echo "Starting Daphne ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 server.asgi:application
