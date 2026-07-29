#!/usr/bin/env sh
set -eu

uv run finalboss migrate
uv run finalboss doctor --strict
uv run finalboss run
