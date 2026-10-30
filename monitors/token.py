"""Print the action token the dashboard asks for.

    docker exec sheltie python -m monitors.token

Only someone who can run commands on the server can read it, which is the point:
the token is never written to the logs.
"""

import sys

import yaml

from monitors.api import GENERATED_TOKEN_KEY
from monitors.config import env
from monitors.state import StateStore

CONFIG_PATH = "config/config.yml"
STATE_PATH = "state/state.json"


def current_token() -> str | None:
    """The token the API checks, chosen the same way as resolve_action_token, without generating one."""
    configured = env("ACTION_TOKEN")
    if configured:
        return configured
    try:
        with open(CONFIG_PATH, encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}
    except OSError:
        config = {}
    from_config = (config.get("actions") or {}).get("token")
    if from_config:
        return str(from_config)
    generated = StateStore(STATE_PATH).get(GENERATED_TOKEN_KEY)
    return str(generated) if generated else None


def main() -> int:
    token = current_token()
    if not token:
        print("No action token yet. Start Sheltie once and it will create one.", file=sys.stderr)
        return 1
    print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
