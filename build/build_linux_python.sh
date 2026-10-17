#!/bin/bash
# Cria dist/Limpador-linux.tar.gz SEM PyInstaller, para qualquer distro
# (Fedora, Arch, openSUSE...). Instala só para o utilizador, sem sudo.
# Uso: tar xzf Limpador-linux.tar.gz && cd Limpador-linux && ./install.sh
set -e
cd "$(dirname "$0")/.."
[ -f icons/icon_256.png ] || python3 make_icons.py
PKG="dist/Limpador-linux"
rm -rf "$PKG" && mkdir -p "$PKG"
install -m 755 limpador.py "$PKG/limpador.py"
install -m 644 icons/icon_256.png "$PKG/limpador.png"
install -m 755 ram/limpador_ram.py "$PKG/limpador_ram.py"
cat > "$PKG/install.sh" <<'INST'
#!/bin/bash
set -e
AQUI="$(cd "$(dirname "$0")" && pwd)"
command -v python3 >/dev/null || { echo "Precisa do python3. Instala-o pelo gestor de pacotes da tua distro."; exit 1; }
mkdir -p "$HOME/.local/share/limpador" "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons"
install -m 755 "$AQUI/limpador.py" "$HOME/.local/share/limpador/limpador.py"
printf '#!/bin/sh\nexec python3 "%s" "$@"\n' "$HOME/.local/share/limpador/limpador.py" > "$HOME/.local/bin/limpador"
chmod 755 "$HOME/.local/bin/limpador"
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
install -m 755 "$AQUI/limpador_ram.py" "$HOME/.local/share/limpador/limpador_ram.py"
printf '#!/bin/sh\nexec python3 "%s" "$@"\n' "$HOME/.local/share/limpador/limpador_ram.py" > "$HOME/.local/bin/limpador-ram"
chmod 755 "$HOME/.local/bin/limpador-ram"
cat > "$HOME/.local/share/applications/limpador-ram.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Limpador RAM
Comment=Memória em tempo real: vê o que está a pesar e fecha o que não precisas
Exec=$HOME/.local/bin/limpador-ram
Icon=$HOME/.local/share/icons/limpador.png
Terminal=false
Categories=System;Monitor;Utility;
DESK
echo "Instalado. Procura 'Limpador' e 'Limpador RAM' no menu de aplicações."
INST
chmod 755 "$PKG/install.sh"
tar -czf dist/Limpador-linux.tar.gz -C dist Limpador-linux
rm -rf "$PKG"
echo "Pronto: dist/Limpador-linux.tar.gz"
