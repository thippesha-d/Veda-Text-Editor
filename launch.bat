@echo off
REM Automatically activate the virtual environment and launch the app
if not exist "venv\" (
    echo Virtual environment not found. Please create it first.
    pause
    exit /b
)
call venv\Scripts\activate.bat
python -m backend.main
pause
