@echo off
setlocal
cd /d "%~dp0"
call "%~dp0runtime.cmd"
"%PDF_PYTHON%" "%~dp0pdf_outline.py" >"%~dp0startup-error.log" 2>&1
if errorlevel 1 (
  echo PDF tool could not start. See startup-error.log in this folder.
  type "%~dp0startup-error.log"
  pause
  exit /b 1
)
endlocal
