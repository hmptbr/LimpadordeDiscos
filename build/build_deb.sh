#!/bin/bash
# Cria dist/limpador_1.0_amd64.deb (instala com duplo clique no Ubuntu/Debian/Mint).
# Pré-requisito: dist/Limpador (binário do build_linux.sh). Correr: bash build/build_deb.sh
set -e
cd "$(dirname "$0")/.."
VERSAO="1.0"
ARQ="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
BIN="${1:-dist/Limpador}"
[ -f "$BIN" ] || { echo "Falta $BIN (corre primeiro build/build_linux.sh)"; exit 1; }
[ -f icons/icon_256.png ] || python3 make_icons.py

PKG="dist/deb/limpador_${VERSAO}_${ARQ}"
rm -rf dist/deb && mkdir -p "$PKG/DEBIAN" "$PKG/opt/limpador" "$PKG/usr/bin" \
  "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps"

install -m 755 "$BIN" "$PKG/opt/limpador/Limpador"
ln -s /opt/limpador/Limpador "$PKG/usr/bin/limpador"
install -m 644 icons/icon_256.png "$PKG/usr/share/icons/hicolor/256x256/apps/limpador.png"

cat > "$PKG/usr/share/applications/limpador.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Limpador
Comment=Liberta espaço no disco com segurança / Free up disk space safely
Exec=/usr/bin/limpador
Icon=limpador
Terminal=true
Categories=System;Utility;
DESK

cat > "$PKG/DEBIAN/control" <<CTRL
Package: limpador
Version: ${VERSAO}
Section: utils
Priority: optional
Architecture: ${ARQ}
Maintainer: Limpador <noreply@example.com>
Description: Liberta espaço no disco com segurança
 Analisa o computador, explica o que ocupa espaço e só apaga depois
 de confirmares. Free up disk space safely.
CTRL

cat > "$PKG/DEBIAN/postinst" <<'POST'
#!/bin/sh
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
exit 0
POST
chmod 755 "$PKG/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$PKG" "dist/limpador_${VERSAO}_${ARQ}.deb" >/dev/null
rm -rf dist/deb
echo "Pronto: dist/limpador_${VERSAO}_${ARQ}.deb"
