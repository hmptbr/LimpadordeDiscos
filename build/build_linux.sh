#!/bin/bash
# Cria dist/Limpador (binário único) e o pacote dist/Limpador-linux.tar.gz com atalho de menu.
# Correr:  bash build/build_linux.sh
set -e
cd "$(dirname "$0")/.."
[ -f icons/icon_256.png ] || python3 make_icons.py

# ambiente virtual próprio (evita mexer no Python do sistema)
python3 -m venv build/.venv
. build/.venv/bin/activate
pip install --quiet pyinstaller
pyinstaller --onefile --console --name Limpador limpador.py >/dev/null
deactivate

PKG=dist/Limpador-linux
rm -rf "$PKG" && mkdir -p "$PKG"
cp dist/Limpador "$PKG/Limpador"
cp icons/icon_256.png "$PKG/limpador.png"

cat > "$PKG/install.sh" <<'INST'
#!/bin/bash
# Instala o Limpador no teu utilizador (sem sudo) e cria o atalho no menu de aplicações.
set -e
AQUI="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons"
install -m 755 "$AQUI/Limpador" "$HOME/.local/bin/limpador"
cp "$AQUI/limpador.png" "$HOME/.local/share/icons/limpador.png"
cat > "$HOME/.local/share/applications/limpador.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Limpador
Comment=Liberta espaço no disco com segurança / Free up disk space safely
Exec=$HOME/.local/bin/limpador
Icon=$HOME/.local/share/icons/limpador.png
Terminal=true
Categories=System;Utility;
DESK
echo "Instalado. Procura 'Limpador' no menu de aplicações, ou corre: limpador"
INST
chmod +x "$PKG/install.sh"

tar -czf dist/Limpador-linux.tar.gz -C dist Limpador-linux
echo "Pronto: dist/Limpador-linux.tar.gz"
