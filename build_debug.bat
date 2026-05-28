@echo off
echo ========================================
echo Building P2P File Sharing - DEBUG MODE
echo ========================================
echo.

REM Clean previous builds
echo [1/3] Cleaning previous builds...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

REM Build with PyInstaller
echo.
echo [2/3] Building executable with PyInstaller...
pyinstaller --clean --noconfirm P2PFileSharing.spec

REM Check if build was successful
if exist "dist\P2PFileSharing.exe" (
    echo.
    echo [3/3] Build successful!
    echo ========================================
    echo Executable location: dist\P2PFileSharing.exe
    echo ========================================
    echo.
    echo You can now copy dist\P2PFileSharing.exe to other PCs for testing.
    echo.
) else (
    echo.
    echo [ERROR] Build failed! Check the output above for errors.
    echo.
    pause
    exit /b 1
)

pause
