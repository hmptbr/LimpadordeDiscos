@echo off
REM Cria dist\Limpador.exe (duplo clique abre a janela do programa).
REM Requer Python 3.8+ instalado.   Correr:  build\build_windows.bat
cd /d "%~dp0\.."
if not exist icons\icon.ico python make_icons.py
python -m pip install --quiet pyinstaller pillow numpy
python -m PyInstaller --onefile --console --name Limpador --icon icons\icon.ico limpador.py
echo.
echo Pronto: dist\Limpador.exe
pause
