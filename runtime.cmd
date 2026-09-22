@echo off
set "PDF_PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PDF_PYTHON=%~dp0.venv\Scripts\python.exe"
set "PYTHONPATH=%~dp0.gpu-libs;%~dp0.ocr-libs;%PYTHONPATH%"
set "PYTHONIOENCODING=utf-8"
exit /b 0
