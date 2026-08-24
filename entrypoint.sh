#!/bin/sh
set -e

echo "Применяю миграции базы данных..."
alembic upgrade head

echo "Запускаю сервер..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
