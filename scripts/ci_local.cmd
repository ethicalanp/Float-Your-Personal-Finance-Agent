@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo [CI Local] Initializing throwaway database float_ci...
echo ===================================================

docker exec -i float-postgres psql -U float -d postgres -c "DROP DATABASE IF EXISTS float_ci WITH (FORCE);" >nul 2>&1
if errorlevel 1 (
    echo FAIL: Could not drop database float_ci in float-postgres container.
    exit /b 1
)

docker exec -i float-postgres psql -U float -d postgres -c "CREATE DATABASE float_ci;" >nul 2>&1
if errorlevel 1 (
    echo FAIL: Could not create database float_ci in float-postgres container.
    exit /b 1
)

cd /d "%~dp0..\apps\api" || (
    echo FAIL: Could not change directory to apps\api.
    exit /b 1
)

set PFA_APP_ENV=test
set PFA_DATABASE_URL=postgresql+psycopg://float:float_dev_password_change_me@localhost:5432/float_ci

set PYTHON_CMD=python
if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" set PYTHON_CMD="%VIRTUAL_ENV%\Scripts\python.exe"
) else (
    if exist "%~dp0..\venv\Scripts\python.exe" set PYTHON_CMD="%~dp0..\venv\Scripts\python.exe"
)

echo [Step 1/5] python -m ruff check .
%PYTHON_CMD% -m ruff check .
if errorlevel 1 (
    echo Step 1/5 - ruff check: FAIL
    exit /b 1
)
echo Step 1/5 - ruff check: PASS

echo [Step 2/5] python -m mypy app --ignore-missing-imports
%PYTHON_CMD% -m mypy app --ignore-missing-imports
if errorlevel 1 (
    echo Step 2/5 - mypy app: FAIL
    exit /b 1
)
echo Step 2/5 - mypy app: PASS

echo [Step 3/5] python -m alembic upgrade head
%PYTHON_CMD% -m alembic upgrade head
if errorlevel 1 (
    echo Step 3/5 - alembic upgrade head: FAIL
    exit /b 1
)
echo Step 3/5 - alembic upgrade head: PASS

echo [Step 4/5] python -m alembic check
%PYTHON_CMD% -m alembic check
if errorlevel 1 (
    echo Step 4/5 - alembic check: FAIL
    exit /b 1
)
echo Step 4/5 - alembic check: PASS

echo [Step 5/5] python -m pytest -q
%PYTHON_CMD% -m pytest -q
if errorlevel 1 (
    echo Step 5/5 - pytest -q: FAIL
    exit /b 1
)
echo Step 5/5 - pytest -q: PASS

echo ===================================================
echo [CI Local] All checks PASSED successfully!
echo ===================================================
exit /b 0
