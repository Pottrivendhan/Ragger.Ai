@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo [Windows Sandbox] Ragger.ai Clean Machine Installation Test
echo ============================================================

echo 1. Checking absence of developer tools...
where python >nul 2>&1
if %errorlevel% equ 0 (
    echo WARNING: python found on PATH in sandbox!
) else (
    echo [PASS] Confirmed: No Python installed on host.
)

where node >nul 2>&1
if %errorlevel% equ 0 (
    echo WARNING: node found on PATH in sandbox!
) else (
    echo [PASS] Confirmed: No Node.js installed on host.
)

where git >nul 2>&1
if %errorlevel% equ 0 (
    echo WARNING: git found on PATH in sandbox!
) else (
    echo [PASS] Confirmed: No Git installed on host.
)

echo.
echo 2. Running silent installer: C:\RaggerDist\RaggerAI-Setup.exe /S
start /wait C:\RaggerDist\RaggerAI-Setup.exe /S

echo.
echo 3. Verifying per-user installation target...
set "APP_DIR=%LOCALAPPDATA%\Programs\Ragger.ai"
if not exist "%APP_DIR%\Ragger.ai.exe" (
    echo [FATAL] Target executable not found at: %APP_DIR%\Ragger.ai.exe
    pause
    exit /b 1
)
echo [PASS] Installed executable found at: %APP_DIR%\Ragger.ai.exe

echo.
echo 4. Verifying frozen hermetic engine...
if not exist "%APP_DIR%\resources\engine\ragger-engine.exe" (
    echo [FATAL] Frozen engine not found at: %APP_DIR%\resources\engine\ragger-engine.exe
    pause
    exit /b 1
)
echo [PASS] Frozen engine found at: %APP_DIR%\resources\engine\ragger-engine.exe

echo.
echo 5. Running packaged application smoke test...
"%APP_DIR%\Ragger.ai.exe" --check-packaged-smoke
if %errorlevel% neq 0 (
    echo [FATAL] Packaged application failed smoke test with exit code %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo [Windows Sandbox] CLEAN MACHINE VERIFICATION PASSED (EXIT CODE 0)
echo ============================================================
pause
exit /b 0
