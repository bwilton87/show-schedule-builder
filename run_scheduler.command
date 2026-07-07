#!/bin/zsh

set -e

PROJECT_DIR="${0:A:h}"
PYTHON="$PROJECT_DIR/.venv313/bin/python"
APP="$PROJECT_DIR/scheduler_gui.py"

cd "$PROJECT_DIR"

if [[ ! -x "$PYTHON" ]]; then
    echo "Could not find the Python 3.13 scheduler environment:"
    echo "$PYTHON"
    echo
    echo "Ask Codex to rebuild .venv313 before launching the app."
    read -r "?Press Enter to close this window."
    exit 1
fi

"$PYTHON" "$APP"
