@echo off
cd /d "%~dp0"
if not exist ".installed" (
    echo Installing dependencies...
    pip install -e ".[web]"
    if errorlevel 1 ( pause & exit /b 1 )
    echo. > .installed
)
echo Starting Class Up...
python -c "from class_up.api.app import start; start()"
pause
