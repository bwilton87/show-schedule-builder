#!/bin/zsh

set -e

PROJECT_DIR="${0:A:h}"
APP_BUNDLE="$PROJECT_DIR/Horse Show Scheduler.app"
MACOS_DIR="$APP_BUNDLE/Contents/MacOS"
LAUNCHER="$MACOS_DIR/Horse Show Scheduler"
LAUNCHER_SOURCE="$PROJECT_DIR/mac_app_launcher.c"

mkdir -p "$MACOS_DIR"

if [[ ! -f "$LAUNCHER_SOURCE" ]]; then
    echo "Could not find native launcher source:"
    echo "$LAUNCHER_SOURCE"
    read -r "?Press Enter to close this window."
    exit 1
fi

/usr/bin/clang "$LAUNCHER_SOURCE" -o "$LAUNCHER"
chmod +x "$LAUNCHER"

echo "Horse Show Scheduler.app is ready:"
echo "$APP_BUNDLE"
echo
echo "You can launch it from Finder like a normal app."
