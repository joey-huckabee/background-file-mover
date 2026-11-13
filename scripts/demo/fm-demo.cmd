@echo off
rem Windows wrapper for scripts/demo/fm-demo.py (development and demos only).
rem Usage: scripts\demo\fm-demo.cmd COMMAND [OPTIONS]   (fm-demo.cmd -h for help)
rem Set FM_DEMO_DISTRO to use a WSL distribution other than Ubuntu.
setlocal
if "%FM_DEMO_DISTRO%"=="" set "FM_DEMO_DISTRO=Ubuntu"
for /f "delims=" %%p in ('wsl.exe -d %FM_DEMO_DISTRO% -e wslpath -a "%~dp0fm-demo.py"') do set "FM_DEMO_SCRIPT=%%p"
if "%FM_DEMO_SCRIPT%"=="" (
  echo fm-demo: could not locate the script inside WSL distribution %FM_DEMO_DISTRO%
  exit /b 1
)
wsl.exe -d %FM_DEMO_DISTRO% -u root -- python3 "%FM_DEMO_SCRIPT%" %*
exit /b %ERRORLEVEL%
