@echo off
setlocal enabledelayedexpansion

echo === [1/2] Backend dependency audit (pip-audit) ===
pushd "%~dp0..\apps\api"
python -m pip_audit
set PIP_AUDIT_EXIT=%ERRORLEVEL%
popd

echo === [2/2] Frontend dependency audit (npm audit) ===
pushd "%~dp0..\apps\web"
call npm audit --audit-level=high
set NPM_AUDIT_EXIT=%ERRORLEVEL%
popd

if not "%PIP_AUDIT_EXIT%"=="0" exit /b %PIP_AUDIT_EXIT%
if not "%NPM_AUDIT_EXIT%"=="0" exit /b %NPM_AUDIT_EXIT%
echo All dependency audits passed.
