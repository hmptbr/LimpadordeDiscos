#!/bin/bash
# Cria Limpador.app (duplo clique abre o Terminal) e Limpador.dmg.
# Correr num Mac:  bash build/build_mac.sh
set -e
cd "$(dirname "$0")/.."
RAIZ="$(pwd)"
APP="dist/Limpador.app"

[ -f icons/icon.icns ] || python3 make_icons.py

rm -rf "$APP" dist/Limpador.dmg dist/dmg
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# 1) Programa: binário PyInstaller (se existir) ou o próprio script Python
if command -v pyinstaller >/dev/null 2>&1; then
  echo "A compilar com PyInstaller..."
  pyinstaller --onefile --console --name Limpador-bin --distpath dist/bin --workpath build/tmp --specpath build/tmp limpador.py >/dev/null
  cp dist/bin/Limpador-bin "$APP/Contents/Resources/Limpador-bin"
else
  echo "PyInstaller não encontrado: a usar o Python do sistema (pip install pyinstaller para um binário único)."
fi
cp limpador.py "$APP/Contents/Resources/limpador.py"
cp icons/icon.icns "$APP/Contents/Resources/icon.icns"

# 2) Lançador: abre o Terminal e corre o programa
cat > "$APP/Contents/MacOS/Limpador" <<'LAUNCH'
#!/bin/bash
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
if [ -x "$RES/Limpador-bin" ]; then
  CMD="'$RES/Limpador-bin'"
else
  CMD="/usr/bin/env python3 '$RES/limpador.py'"
fi
osascript <<OSA
tell application "Terminal"
  activate
  do script "clear; $CMD; exit"
end tell
OSA
LAUNCH
chmod +x "$APP/Contents/MacOS/Limpador"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Limpador</string>
  <key>CFBundleDisplayName</key><string>Limpador</string>
  <key>CFBundleIdentifier</key><string>app.limpador.cleaner</string>
  <key>CFBundleExecutable</key><string>Limpador</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSAppleEventsUsageDescription</key><string>O Limpador abre o Terminal para mostrar o que pode ser apagado.</string>
</dict></plist>
PLIST

# 3) Assinatura "ad-hoc" (evita alguns avisos; não substitui um Developer ID)
codesign --force --deep --sign - "$APP" 2>/dev/null || true

# 4) DMG
mkdir -p dist/dmg && cp -R "$APP" dist/dmg/ && ln -s /Applications dist/dmg/Applications
hdiutil create -volname "Limpador" -srcfolder dist/dmg -ov -format UDZO dist/Limpador.dmg >/dev/null
rm -rf dist/dmg
# 5) Instalador .pkg (duplo clique -> instala em Aplicações)
pkgbuild --component "$APP" --install-location /Applications dist/Limpador.pkg >/dev/null
echo "Pronto: dist/Limpador.app, dist/Limpador.dmg e dist/Limpador.pkg"
