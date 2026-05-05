#!/usr/bin/env bash

set -u

echo "STAGE_START pwd=$(pwd)"
echo "STAGE_FILES"
ls -la
echo "STAGE_ENV_KEYS"
env | grep -E "^(BOT_TOKEN|DATABASE_URL|REDIS_URL|OWNER_TELEGRAM_ID|DEFAULT_ACCESS_CODE)=" | sed 's/=.*/=<set>/'

echo "STAGE_ALEMBIC"
alembic upgrade head
ALEMBIC_EXIT=$?
echo "STAGE_ALEMBIC_EXIT=${ALEMBIC_EXIT}"
if [ "${ALEMBIC_EXIT}" -ne 0 ]; then
  echo "ALEMBIC_FAILED"
  exit ${ALEMBIC_EXIT}
fi

echo "STAGE_SEED"
python -u -m scripts.seed_questions
SEED_EXIT=$?
echo "STAGE_SEED_EXIT=${SEED_EXIT}"
if [ "${SEED_EXIT}" -ne 0 ]; then
  echo "SEED_FAILED_BUT_CONTINUING"
fi

echo "STAGE_BOT"
exec python -u -m pylevelup
