#!/bin/bash
set -e
cd "$(dirname "$0")"

swift build 2>&1

APP_DIR=".build/AgentApp.app/Contents/MacOS"
mkdir -p "$APP_DIR"
cp .build/arm64-apple-macosx/debug/AgentApp "$APP_DIR/AgentApp"

cat > .build/AgentApp.app/Contents/Info.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>AgentApp</string>
    <key>CFBundleIdentifier</key><string>com.agent.d15</string>
    <key>CFBundleName</key><string>AgentApp</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>NSPrincipalClass</key><string>NSApplication</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

open .build/AgentApp.app
