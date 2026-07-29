#!/usr/bin/env sh
set -eu

python -m pip install --disable-pip-version-check uv==0.12.0
uv sync --frozen --no-dev
