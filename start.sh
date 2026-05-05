#!/usr/bin/env bash

set -eu

alembic upgrade head
python -u -m scripts.seed_questions
python -u -m scripts.seed_achievements
exec python -u -m pylevelup
