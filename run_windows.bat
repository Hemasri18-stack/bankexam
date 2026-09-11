@echo off
cd /d "%~dp0app"
echo Starting Bank Exam Prep Manager...
echo Once it says "running at http://localhost:8000", open that address in your browser.
echo Press Ctrl+C in this window to stop the server.
python server.py
pause
