#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$HOME/.local/bin:$PATH"
exec uv run --project "$project_dir" --locked python "$project_dir/tools/benchmark_tools.py" "$@"
