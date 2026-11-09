#!/bin/bash
cd "$(dirname "$0")"; set -a; source ./.env; set +a
exec python3 ask.py --serve --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}"
