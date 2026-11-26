@echo off
setlocal
cd /d "%~dp0..\apps\api" || exit /b 1

set PFA_APP_ENV=development
set PYTHON_CMD=python
if exist "%~dp0..\venv\Scripts\python.exe" set PYTHON_CMD="%~dp0..\venv\Scripts\python.exe"

echo [Running Real-Embedder PolicyGuard Integration Test]
%PYTHON_CMD% -m pytest -v -m real_embedder tests/ai/test_policy_guard.py
