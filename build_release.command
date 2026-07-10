#!/bin/zsh

set -e

PROJECT_DIR="${0:A:h}"
PYTHON="$PROJECT_DIR/.venv313/bin/python"
DIST_DIR="$PROJECT_DIR/release"
BUILD_DIR="$PROJECT_DIR/build/pyinstaller"
APP_NAME="Show Schedule Builder"
PACKAGE_DIR="$DIST_DIR/$APP_NAME Release"

export COPYFILE_DISABLE=1

cd "$PROJECT_DIR"

if [[ ! -x "$PYTHON" ]]; then
    echo "Could not find the Python 3.13 scheduler environment:"
    echo "$PYTHON"
    read -r "?Press Enter to close this window."
    exit 1
fi

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller is not installed in .venv313."
    echo "Install it with:"
    echo "$PYTHON -m pip install pyinstaller"
    read -r "?Press Enter to close this window."
    exit 1
fi

rm -rf "$DIST_DIR" "$BUILD_DIR"
mkdir -p "$DIST_DIR" "$BUILD_DIR"

"$PYTHON" -m PyInstaller \
    --name "$APP_NAME" \
    --windowed \
    --noconfirm \
    --clean \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR" \
    --specpath "$BUILD_DIR" \
    --add-data "$PROJECT_DIR/web_static:web_static" \
    --hidden-import "pypdfium2" \
    web_scheduler.py

cat > "$DIST_DIR/README - Start Here.txt" <<'README'
Show Schedule Builder

1. Double-click Show Schedule Builder.app.
2. Your browser will open to the local schedule builder.
3. Paste the show URLs, select riders, and click Generate and Download Excel.

The app runs locally on your Mac. It needs internet access only to read the show
software URLs that you paste into the page.

If macOS says the app cannot be opened because it is from an unidentified
developer, Control-click the app, choose Open, then choose Open again.
README

rm -rf "$PACKAGE_DIR" "$DIST_DIR/$APP_NAME.zip"
mkdir -p "$PACKAGE_DIR"
ditto "$DIST_DIR/$APP_NAME.app" "$PACKAGE_DIR/$APP_NAME.app"
cp "$DIST_DIR/README - Start Here.txt" "$PACKAGE_DIR/README - Start Here.txt"
find "$PACKAGE_DIR" -name '._*' -delete
(
    cd "$DIST_DIR"
    /usr/bin/zip -qryX "$APP_NAME.zip" "$APP_NAME Release"
)

echo "Release build complete:"
echo "$DIST_DIR/$APP_NAME.app"
echo "$PACKAGE_DIR"
echo "$DIST_DIR/$APP_NAME.zip"
