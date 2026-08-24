: << 'CMDBLOCK'
@echo off
REM Cross-platform polyglot wrapper for hook scripts.
REM On Windows: cmd.exe runs the batch portion, which finds and calls bash.
REM On Unix: the shell interprets this as a script (: is a no-op in bash).
REM
REM Hook scripts use extensionless filenames (e.g. "session-start" not
REM "session-start.sh") so Claude Code's Windows auto-detection -- which
REM prepends "bash" to any command containing .sh -- doesn't interfere.
REM
REM Discovery picks a bash first and runs it once, at :run. Doing the work in
REM one place is what lets the hook's exit code survive: `exit /b %ERRORLEVEL%`
REM inside a parenthesised if-block expands when the block is parsed, which is
REM before the hook has run, so every hook used to look like it succeeded no
REM matter how it exited.
REM
REM Usage: run-hook.cmd <script-name> [args...]

if "%~1"=="" (
    echo run-hook.cmd: missing script name >&2
    exit /b 1
)

set "HOOK_DIR=%~dp0"
set "HOOK_BASH="

REM Git for Windows in its standard locations
if exist "C:\Program Files\Git\bin\bash.exe" set "HOOK_BASH=C:\Program Files\Git\bin\bash.exe"
if not defined HOOK_BASH if exist "C:\Program Files (x86)\Git\bin\bash.exe" set "HOOK_BASH=C:\Program Files (x86)\Git\bin\bash.exe"
if defined HOOK_BASH goto :run

REM Git installed somewhere else: derive bash from where git itself lives,
REM so a non-default install is found without guessing at paths.
REM   <root>\cmd\git.exe  ->  <root>\bin\bash.exe
set "HOOK_GIT="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined HOOK_GIT set "HOOK_GIT=%%G"
if not defined HOOK_GIT goto :pathbash
call :parentdir "%HOOK_GIT%"
if exist "%HOOK_GITROOT%bin\bash.exe" set "HOOK_BASH=%HOOK_GITROOT%bin\bash.exe"
if defined HOOK_BASH goto :run

:pathbash
REM bash on PATH (MSYS2, Cygwin), but only if it really is one of those.
REM With WSL installed, `where bash` finds C:\Windows\System32\bash.exe -- the
REM WSL launcher, which cannot open a Windows path. Handing it the hook starts
REM WSL only to fail, so check what kind of bash it is before using it.
where bash >nul 2>nul
if errorlevel 1 goto :nobash
set "HOOK_FLAVOUR="
for /f "delims=" %%F in ('bash -c "uname -o" 2^>nul') do if not defined HOOK_FLAVOUR set "HOOK_FLAVOUR=%%F"
if "%HOOK_FLAVOUR%"=="Msys" set "HOOK_BASH=bash"
if "%HOOK_FLAVOUR%"=="Cygwin" set "HOOK_BASH=bash"
if not defined HOOK_BASH goto :nobash

:run
"%HOOK_BASH%" "%HOOK_DIR%%~1" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:nobash
REM No usable bash found - exit silently rather than error
REM (plugin still works, just without SessionStart context injection)
exit /b 0

:parentdir
REM The directory holding %1's own directory: <root>\cmd\git.exe -> <root>\
set "HOOK_GITROOT=%~dp1"
set "HOOK_GITROOT=%HOOK_GITROOT:~0,-1%"
for %%P in ("%HOOK_GITROOT%") do set "HOOK_GITROOT=%%~dpP"
goto :eof
CMDBLOCK

# Unix: run the named script directly
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_NAME="$1"
shift
exec bash "${SCRIPT_DIR}/${SCRIPT_NAME}" "$@"
