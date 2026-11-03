#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$HOME/.local/bin:$PATH"
exec uv run --project "$project_dir" --locked --group vision python "$project_dir/tools/benchmark_vision.py" "$@"
