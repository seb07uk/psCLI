:: Sebastian Januchowski
:: polsoft.its@fastservice.com
:: https://github.com/seb07uk
@echo off
setlocal enabledelayedexpansion

:: --- CONFIGURATION ---
set "LOG_FILE=C:\Users\%userprofile%\.polsoft\psCLI\Log\debugger_trace.log"
set "VER=2.1 (Pro)"

:: --- COLORS ---
set "ESC= "
set "RST=%ESC%[0m"
set "RED=%ESC%[91m"
set "GRN=%ESC%[92m"
set "YLW=%ESC%[93m"
set "BLU=%ESC%[94m"
set "CYN=%ESC%[96m"
set "GRA=%ESC%[90m"
set "WHT=%ESC%[97m"

:: --- ARGUMENTS ---
set "ACTION=%~1"
set "MSG=%~2"

:: --- HELP DISPATCHER ---
if "%ACTION%"=="" goto :help
if "%ACTION%"=="/?" goto :help
if /I "%ACTION%"=="help" goto :help
if /I "%ACTION%"=="--help" goto :help

:: --- TOOLS & FUNCTIONS ---
if /I "%ACTION%"=="clean" (
    del "%LOG_FILE%" 2>nul
    echo %GRN%[SYSTEM]%RST% Log file "%LOG_FILE%" has been cleared.
    exit /b 0
)

if /I "%ACTION%"=="trace" (
    echo %GRA%[TRACE] User:%USERNAME% ^| Host:%COMPUTERNAME% ^| OS:%OS% ^| PWD:%CD%%RST%
    exit /b 0
)

:: --- SCRIPT EXECUTION HANDLER (.py / .ps1 / .exe) ---
for %%X in (.py .ps1 .exe) do (
    if /I "%ACTION:~-3%"=="%%~X" (
        set "SCRIPT=%ACTION%"
        set "TS=%time:~0,8%"
        echo %CYN%[%TS%] [EXEC] Running script: %SCRIPT%%RST%
        (echo [%date% %time%] [EXEC] Running script: %SCRIPT%) >> "%LOG_FILE%" 2>nul

        if /I "%%~X"==".py" (
            python "%SCRIPT%" %MSG%
            exit /b %errorlevel%
        )

        if /I "%%~X"==".ps1" (
            powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %MSG%
            exit /b %errorlevel%
        )

        if /I "%%~X"==".exe" (
            "%SCRIPT%" %MSG%
            exit /b %errorlevel%
        )
    )
)

:: --- LOGGING LOGIC ---
set "LVL=INFO" & set "CLR=%BLU%"
if /I "%ACTION%"=="i"   (set "LVL=INFO   " & set "CLR=%BLU%")
if /I "%ACTION%"=="s"   (set "LVL=SUCCESS" & set "CLR=%GRN%")
if /I "%ACTION%"=="ok"  (set "LVL=SUCCESS" & set "CLR=%GRN%")
if /I "%ACTION%"=="w"   (set "LVL=WARN   " & set "CLR=%YLW%")
if /I "%ACTION%"=="e"   (set "LVL=ERROR  " & set "CLR=%RED%")
if /I "%ACTION%"=="err" (set "LVL=ERROR  " & set "CLR=%RED%")

:: If no alias matched, use the input as custom level
if "%CLR%"=="%BLU%" if /I NOT "%ACTION%"=="i" if /I NOT "%ACTION%"=="info" (
    set "LVL=%ACTION%"
    set "CLR=%CYN%"
)

:: Validation
if "%MSG%"=="" (
    echo %RED%[ERROR]%RST% No message provided. Use: debug %ACTION% "message"
    exit /b 1
)

:: Output
set "TS=%time:~0,8%"
echo %CLR%[%TS%] [%LVL%] %MSG%%RST%
(echo [%date% %time%] [%LVL%] %MSG%) >> "%LOG_FILE%" 2>nul
exit /b 0

:: =====================================================================
:: EXTENDED HELP SECTION
:: =====================================================================
:help
echo %WHT%=====================================================================%RST%
echo    %CYN%DEBUG MODULE v%VER%%RST% - Advanced Batch Logging Engine
echo %WHT%=====================================================================%RST%
echo.
echo %WHT%USAGE:%RST%
echo   %GRN%debug%RST% [level/alias] "message"
echo   %GRN%call debug%RST% [level/alias] "message" %GRA%(within .bat files)%RST%
echo.
echo %WHT%LOGGING LEVELS ^& ALIASES:%RST%
echo   %BLU%INFO%RST%    (alias: %BLU%i%RST%)      - General system information
echo   %GRN%SUCCESS%RST% (alias: %GRN%s, ok%RST%)  - Positive task completion
echo   %YLW%WARN%RST%    (alias: %YLW%w%RST%)      - Non-critical issues or warnings
echo   %RED%ERROR%RST%   (alias: %RED%e, err%RST%) - Failures and critical problems
echo.
echo   %CYN%CUSTOM%RST%  - Any other string will be used as a level
echo.
echo %WHT%SYSTEM COMMANDS:%RST%
echo   %WHT%clean%RST%  - Deletes the current log file (%LOG_FILE%)
echo   %WHT%trace%RST%  - Prints current user, machine, and path context
echo   %WHT%help%RST%   - Displays this extended documentation
echo.
echo %WHT%SCRIPT EXECUTION:%RST%
echo   debug script.py "arg"
echo   debug script.ps1 "arg"
echo   debug program.exe "/silent"
echo.
echo %GRA%Logs are automatically saved to: %LOG_FILE%%RST%
echo %WHT%=====================================================================%RST%
exit /b 0