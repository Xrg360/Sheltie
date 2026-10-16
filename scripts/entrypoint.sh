#!/bin/bash
# One process: the Python monitor also serves the dashboard (the static export in ./web)
# on PORT, so there is no Node server at runtime. exec hands tini's SIGTERM straight to it.
set -u

exec python app.py
