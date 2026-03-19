#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Clearing compressor cache..."
rm -rf /app/static/CACHE

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Compressing static files..."
python manage.py compress --force

echo "Starting Daphne ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 server.asgi:application
