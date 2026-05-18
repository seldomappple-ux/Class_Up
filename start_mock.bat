@echo off
cd /d "%~dp0"
pip install -e ".[web]" -q
class-up-mock
pause
