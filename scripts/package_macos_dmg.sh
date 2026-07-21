#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="AutoPaperReader"
SERVER_DIR="dist/AutoPaperReaderServer"
STAGING_DIR="dist/macos"
APP_DIR="$STAGING_DIR/$APP_NAME.app"
DMG_PATH="dist/${APP_NAME}-unsigned.dmg"

if [[ ! -x "$SERVER_DIR/AutoPaperReaderServer" ]]; then
  ./scripts/package_backend.sh
fi

rm -rf "$STAGING_DIR" "$DMG_PATH"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp -R "$SERVER_DIR" "$APP_DIR/Contents/Resources/server"

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>AutoPaperReader</string>
  <key>CFBundleIdentifier</key>
  <string>local.autopaperreader.app</string>
  <key>CFBundleName</key>
  <string>AutoPaperReader</string>
  <key>CFBundleDisplayName</key>
  <string>AutoPaperReader</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
</dict>
</plist>
PLIST

cat > "$APP_DIR/Contents/MacOS/AutoPaperReader" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail

CONTENTS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVER="$CONTENTS_DIR/Resources/server/AutoPaperReaderServer"
export AUTOPAPER_DESKTOP="${AUTOPAPER_DESKTOP:-1}"
export AUTOPAPER_PORT="${AUTOPAPER_PORT:-8765}"

"$SERVER" &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 40); do
  if /usr/bin/curl -fsS "http://127.0.0.1:${AUTOPAPER_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

/usr/bin/open "http://127.0.0.1:${AUTOPAPER_PORT}/"
wait "$SERVER_PID"
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/AutoPaperReader"

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "$DMG_PATH"
