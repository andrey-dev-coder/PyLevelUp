#!/usr/bin/env bash

set -eu

alembic upgrade head
python -u -m scripts.seed_questions
python -u -m scripts.seed_achievements
python -u -m scripts.seed_open_questions
exec python -u -m pylevelup
