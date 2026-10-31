@echo off
rem Opens the PEPA examples and the "play the scammer" page at http://127.0.0.1:8000 (PEPA reads only web pages,
rem not files opened from disk). Open the address in the browser where PEPA is installed. Close the window to stop.
set "PY=%~dp0..\helper\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo Ukazky PEPA bezi na http://127.0.0.1:8000/index.html  (otevrete v prohlizeci s PEPA, ukoncite zavrenim okna)
start "" /b cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000/index.html"
"%PY%" -m http.server 8000 --bind 127.0.0.1 -d "%~dp0."
