@echo off
setlocal
cd /d "%~dp0"
call "%~dp0runtime.cmd"
set "PYTHONPATH="
echo Installing optional CUDA 12 / cuDNN 9 support into this copy only.
echo Please close this PDF tool before installation. Downloads can be large.
"%PDF_PYTHON%" -m pip install --index-url https://pypi.org/simple --upgrade --target "%~dp0.gpu-libs" -r "%~dp0requirements-cuda.txt"
if errorlevel 1 (
  echo Installation failed. You can still run OCR on CPU.
  pause
  exit /b 1
)
echo Installed. Restart the tool and click the device check button.
pause
endlocal
