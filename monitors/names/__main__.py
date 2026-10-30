"""Command line for names.

    docker exec sheltie python -m monitors.names import state/names-import.db

Copies names and settings from another names database (same tables as state/names.db)
into Sheltie. Stop whatever app writes that database first so it is complete, then copy
it into Sheltie's state folder.
"""

import sys

import yaml

from monitors.names.service import UserError, build_names_service

USAGE = "usage: python -m monitors.names import <path to a names database>"


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "import":
        print(USAGE, file=sys.stderr)
        return 2
    with open("config/config.yml", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    service = build_names_service(config)
    if service is None:
        print("Names are turned off. Set SHELTIE_NAMES_ENABLED=1 (or names.enabled: true) first.", file=sys.stderr)
        return 1
    try:
        result = service.import_names(argv[1])
    except UserError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Imported {result['names']} name(s) under {service.zone()}. "
          "Restart Sheltie (docker compose restart sheltie) so the dashboard and proxy pick them up.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
