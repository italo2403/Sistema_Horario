@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Python nao encontrado. Instale Python 3.10+ para COMPILAR o executavel.
  pause
  exit /b 1
)
py -3 -m pip install --upgrade pyinstaller
if errorlevel 1 goto erro
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name GestorHorariosDocentes --add-data "static;static" --add-data "dados_iniciais.sqlite3;." launcher.py
if errorlevel 1 goto erro
echo.
echo EXECUTAVEL GERADO: %~dp0dist\GestorHorariosDocentes.exe
echo Copie o .exe para qualquer PC Windows 10/11 compatível.
pause
exit /b 0
:erro
echo Erro ao criar o executavel. Confira o Python e a conexao para instalar PyInstaller.
pause
exit /b 1
