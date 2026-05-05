#!/usr/bin/env bash

set -eu

alembic upgrade head
python -u -m scripts.seed_questions
exec python -u -m pylevelup
