web: python -m pylevelup
worker: celery -A pylevelup.celery_app.celery_app worker --loglevel=INFO --concurrency=2
beat: celery -A pylevelup.celery_app.celery_app beat --loglevel=INFO
release: alembic upgrade head && python -m scripts.seed_questions
