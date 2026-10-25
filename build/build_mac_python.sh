#!/bin/bash
# Cria os instaladores para macOS SEM PyInstaller e SEM precisar de um Mac:
#   dist/Limpador-mac.zip   (Limpador.app comprimido: descomprime e arrasta para Aplicações)
#   dist/Limpador.dmg       (abre e arrasta para Aplicações)
#   dist/Limpador.pkg       (assistente que instala em Aplicações)
# O Limpador só usa a biblioteca padrão do Python, por isso a app corre o
# limpador.py com o python3 do Mac. Serve para Intel e Apple Silicon.
#
# Num Mac usa hdiutil e pkgbuild. No Linux usa estas ferramentas (se faltarem,
# esse ficheiro é saltado):
#   .dmg -> hfsplus e dmg  (github.com/mozilla/libdmg-hfsplus) + mkfs.hfsplus (apt install hfsprogs)
#   .pkg -> mkbom          (github.com/hogliux/bomutils) + xar (github.com/mackyle/xar) + cpio
# Correr: bash build/build_mac_python.sh
set -e
cd "$(dirname "$0")/.."
VERSAO="${VERSAO:-1.1}"
ID="app.limpador.cleaner"
[ -f icons/icon.icns ] || python3 make_icons.py

APP="dist/mac/Limpador.app"
rm -rf dist/mac dist/Limpador-mac.zip dist/Limpador.dmg dist/Limpador.pkg
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
install -m 644 limpador.py "$APP/Contents/Resources/limpador.py"
install -m 644 icons/icon.icns "$APP/Contents/Resources/icon.icns"

# Lançador: procura um python3 que funcione e abre o Terminal com o menu.
cat > "$APP/Contents/MacOS/Limpador" <<'LAUNCH'
#!/bin/bash
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
PY=""
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  [ -x "$p" ] && { PY="$p"; break; }
done
# /usr/bin/python3 só funciona se as Ferramentas de Linha de Comandos estiverem instaladas
if [ -z "$PY" ] && xcode-select -p >/dev/null 2>&1 && [ -x /usr/bin/python3 ]; then
  PY=/usr/bin/python3
fi
if [ -z "$PY" ]; then
  R=$(osascript -e 'button returned of (display dialog "O Limpador precisa do Python 3, que ainda não está instalado neste Mac.\n\nClica em Instalar: o macOS instala as Ferramentas de Linha de Comandos da Apple (inclui o Python). Depois abre o Limpador outra vez." buttons {"Cancelar", "Instalar"} default button "Instalar" with icon caution with title "Limpador")' 2>/dev/null)
  [ "$R" = "Instalar" ] && xcode-select --install >/dev/null 2>&1
  exit 0
fi
osascript <<OSA
tell application "Terminal"
  activate
  do script "clear; '$PY' '$RES/limpador.py'; exit"
end tell
OSA
LAUNCH
chmod 755 "$APP/Contents/MacOS/Limpador"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Limpador</string>
  <key>CFBundleDisplayName</key><string>Limpador</string>
  <key>CFBundleIdentifier</key><string>${ID}</string>
  <key>CFBundleExecutable</key><string>Limpador</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSAO}</string>
  <key>CFBundleVersion</key><string>${VERSAO}</string>
  <key>LSMinimumSystemVersion</key><string>10.15</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppleEventsUsageDescription</key><string>O Limpador abre o Terminal para mostrar o que pode ser apagado.</string>
</dict></plist>
PLIST
printf 'APPL????' > "$APP/Contents/PkgInfo"
command -v codesign >/dev/null && codesign --force --deep --sign - "$APP" 2>/dev/null || true

# 1) ZIP (o Arquivo do macOS mantém as permissões)
(cd dist/mac && zip -qry ../Limpador-mac.zip Limpador.app)
echo "Pronto: dist/Limpador-mac.zip"

# 2) DMG com atalho para Aplicações
mkdir -p dist/mac/dmg && cp -R "$APP" dist/mac/dmg/
if command -v hdiutil >/dev/null; then
  ln -s /Applications dist/mac/dmg/Applications
  hdiutil create -volname Limpador -srcfolder dist/mac/dmg -ov -format UDZO dist/Limpador.dmg >/dev/null
  echo "Pronto: dist/Limpador.dmg"
elif command -v hfsplus >/dev/null && command -v dmg >/dev/null && command -v mkfs.hfsplus >/dev/null; then
  KB=$(du -sk dist/mac/dmg | cut -f1)
  dd if=/dev/zero of=dist/mac/raw.img bs=1k count=$((KB + 4096)) status=none
  mkfs.hfsplus -v Limpador dist/mac/raw.img >/dev/null
  hfsplus dist/mac/raw.img addall dist/mac/dmg >/dev/null
  hfsplus dist/mac/raw.img chmod 755 /Limpador.app/Contents/MacOS/Limpador >/dev/null
  hfsplus dist/mac/raw.img symlink /Applications /Applications >/dev/null
  dmg dmg dist/mac/raw.img dist/Limpador.dmg >/dev/null
  echo "Pronto: dist/Limpador.dmg"
else
  echo "Sem hdiutil nem hfsplus/dmg: .dmg saltado."
fi

# 3) PKG (instala em /Applications)
if command -v pkgbuild >/dev/null; then
  pkgbuild --component "$APP" --install-location /Applications --identifier "$ID.pkg" \
    --version "$VERSAO" dist/mac/base.pkg >/dev/null
  productbuild --package dist/mac/base.pkg dist/Limpador.pkg >/dev/null
  echo "Pronto: dist/Limpador.pkg"
elif command -v mkbom >/dev/null && command -v xar >/dev/null && command -v cpio >/dev/null; then
  RAIZ="dist/mac/pkgroot" FLAT="dist/mac/flat"
  mkdir -p "$RAIZ" "$FLAT/base.pkg" && cp -R "$APP" "$RAIZ/"
  N=$(find "$RAIZ" | wc -l); KB=$(du -sk "$RAIZ" | cut -f1)
  (cd "$RAIZ" && find . | LC_ALL=C sort | cpio -o --format odc --owner 0:80 --quiet | gzip -c) > "$FLAT/base.pkg/Payload"
  mkbom -u 0 -g 80 "$RAIZ" "$FLAT/base.pkg/Bom"
  cat > "$FLAT/base.pkg/PackageInfo" <<INFO
<pkg-info format-version="2" identifier="$ID.pkg" version="$VERSAO" install-location="/Applications" auth="root">
  <payload numberOfFiles="$N" installKBytes="$KB"/>
</pkg-info>
INFO
  cat > "$FLAT/Distribution" <<DIST
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="1">
  <title>Limpador</title>
  <options customize="never" require-scripts="false" hostArchitectures="x86_64,arm64"/>
  <domains enable_localSystem="true"/>
  <choices-outline><line choice="default"><line choice="$ID.pkg"/></line></choices-outline>
  <choice id="default"/>
  <choice id="$ID.pkg" visible="false"><pkg-ref id="$ID.pkg"/></choice>
  <pkg-ref id="$ID.pkg" version="$VERSAO" onConclusion="none" installKBytes="$KB">#base.pkg</pkg-ref>
</installer-gui-script>
DIST
  OUT="$(pwd)/dist/Limpador.pkg"
  (cd "$FLAT" && xar --compression none -cf "$OUT" Distribution base.pkg)
  echo "Pronto: dist/Limpador.pkg"
else
  echo "Sem pkgbuild nem mkbom/xar/cpio: .pkg saltado."
fi
rm -rf dist/mac
