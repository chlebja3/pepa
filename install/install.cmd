@echo off
rem PEPA installer for Windows: double-click it. Fetches uv (a small Python manager) if missing, then runs install.py.
cd /d "%~dp0"
rem uv, its Python and its download cache stay in this folder: deleting the folder removes everything.
set "UV_CACHE_DIR=%~dp0.uv\cache"
set "UV_PYTHON_INSTALL_DIR=%~dp0.uv\python"
set "UV_INSTALL_DIR=%~dp0.uv\bin"
set "UV_NO_MODIFY_PATH=1"
set "PATH=%~dp0.uv\bin;%PATH%"
where uv >nul 2>nul || powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
uv run --no-project --python 3.12 install.py %*
pause
