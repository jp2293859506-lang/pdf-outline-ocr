@echo off
setlocal
cd /d "%~dp0"
call "%~dp0runtime.cmd"
"%PDF_PYTHON%" -m pip install --index-url https://pypi.org/simple --target "%~dp0.ocr-libs" -r "%~dp0requirements.txt" -r "%~dp0requirements-ocr.txt"
if errorlevel 1 (
  echo Installation failed. See the error above.
  pause
  exit /b 1
)
echo OCR installed. Restart the PDF tool.
pause
endlocal
