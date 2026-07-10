#!/bin/zsh

set -e

PROJECT_DIR="${0:A:h}"
APP_BUNDLE="$PROJECT_DIR/Show Schedule Builder.app"
CONTENTS_DIR="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
LAUNCHER="$MACOS_DIR/Show Schedule Builder"
LAUNCHER_SOURCE="$PROJECT_DIR/web_app_launcher.c"
INFO_PLIST="$CONTENTS_DIR/Info.plist"

mkdir -p "$MACOS_DIR"

if [[ ! -f "$LAUNCHER_SOURCE" ]]; then
    echo "Could not find native web launcher source:"
    echo "$LAUNCHER_SOURCE"
    read -r "?Press Enter to close this window."
    exit 1
fi

/usr/bin/clang "$LAUNCHER_SOURCE" -o "$LAUNCHER"
chmod +x "$LAUNCHER"

cat > "$INFO_PLIST" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleDisplayName</key>
  <string>Show Schedule Builder</string>
  <key>CFBundleExecutable</key>
  <string>Show Schedule Builder</string>
  <key>CFBundleIdentifier</key>
  <string>com.benwilton.showschedulebuilder</string>
  <key>CFBundleName</key>
  <string>Show Schedule Builder</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
</dict>
</plist>
PLIST

printf 'APPL????\n' > "$CONTENTS_DIR/PkgInfo"

echo "Show Schedule Builder.app is ready:"
echo "$APP_BUNDLE"
echo
echo "You can launch it from Finder like a normal app."
