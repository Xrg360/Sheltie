#!/bin/bash
# Runs the Python monitor and the Next.js dashboard side by side under tini.
# SIGTERM from `docker stop` reaches both, and if either process exits the other is
# stopped too, so the container exits and Docker's restart policy brings it back.
set -u

python app.py &
monitor=$!
node node_modules/next/dist/bin/next start -p "${PORT:-8710}" &
web=$!

stop() {
  kill -TERM "$monitor" "$web" 2>/dev/null || true
}
trap stop TERM INT

wait -n "$monitor" "$web"
status=$?
stop
wait "$monitor" "$web" 2>/dev/null
exit "$status"
