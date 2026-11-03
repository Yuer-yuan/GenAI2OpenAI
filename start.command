#!/bin/sh
set -eu

cd -- "$(dirname -- "$0")"
export PATH="$HOME/.local/bin:$PATH"

if [ ! -f .env ]; then
    (umask 077; cp .env.example .env)
fi

exec uv run --locked python main.py "$@"
