#!/bin/bash
# Cria dist/limpador_<versao>_all.deb SEM PyInstaller.
# O Limpador só usa a biblioteca padrão do Python, por isso o pacote instala
# o limpador.py e usa o python3 do sistema. Serve para qualquer arquitetura
# (Intel/AMD, ARM, Raspberry Pi) em Ubuntu, Debian, Mint, Pop!_OS, Zorin...
# Correr: bash build/build_deb_python.sh
set -e
cd "$(dirname "$0")/.."
VERSAO="${VERSAO:-1.1}"
[ -f icons/icon_256.png ] || python3 make_icons.py

PKG="dist/deb/limpador_${VERSAO}_all"
rm -rf dist/deb && mkdir -p "$PKG/DEBIAN" "$PKG/opt/limpador" "$PKG/usr/bin" \
  "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps" \
  "$PKG/usr/share/doc/limpador"

install -m 755 limpador.py "$PKG/opt/limpador/limpador.py"
cat > "$PKG/usr/bin/limpador" <<'RUN'
#!/bin/sh
exec /usr/bin/python3 /opt/limpador/limpador.py "$@"
RUN
chmod 755 "$PKG/usr/bin/limpador"
install -m 644 icons/icon_256.png "$PKG/usr/share/icons/hicolor/256x256/apps/limpador.png"
install -m 644 icons/icon_256.png "$PKG/usr/share/icons/hicolor/256x256/apps/limpador-ram.png"
install -m 755 ram/limpador_ram.py "$PKG/opt/limpador/limpador_ram.py"
cat > "$PKG/usr/bin/limpador-ram" <<'RUN'
#!/bin/sh
exec /usr/bin/python3 /opt/limpador/limpador_ram.py "$@"
RUN
chmod 755 "$PKG/usr/bin/limpador-ram"
cat > "$PKG/usr/share/applications/limpador-ram.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Limpador RAM
Comment=Memória em tempo real: vê o que está a pesar e fecha o que não precisas
Exec=limpador-ram
Icon=limpador-ram
Terminal=false
Categories=System;Monitor;Utility;
Keywords=ram;memória;memory;swap;monitor;
DESK
install -m 644 LICENSE "$PKG/usr/share/doc/limpador/copyright"

cat > "$PKG/usr/share/applications/limpador.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Limpador
Comment=Liberta espaço no disco com segurança / Free up disk space safely
Exec=limpador
Icon=limpador
Terminal=true
Categories=System;Utility;
Keywords=disco;espaço;limpeza;cache;disk;space;cleaner;
DESK

cat > "$PKG/DEBIAN/control" <<CTRL
Package: limpador
Version: ${VERSAO}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.8)
Maintainer: hmptbr <https://github.com/hmptbr/LimpadordeDiscos>
Homepage: https://github.com/hmptbr/LimpadordeDiscos
Recommends: libnotify-bin
Description: Liberta espaço no disco e vigia a memória RAM
 Analisa o computador, explica o que ocupa espaço e só apaga depois
 de confirmares. Inclui o Limpador RAM, um monitor de memória em
 tempo real que fecha apps paradas quando a RAM acaba.
CTRL

cat > "$PKG/DEBIAN/postinst" <<'POST'
#!/bin/sh
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
exit 0
POST
chmod 755 "$PKG/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$PKG" "dist/limpador_${VERSAO}_all.deb" >/dev/null
rm -rf dist/deb
echo "Pronto: dist/limpador_${VERSAO}_all.deb"
