@echo off
chcp 65001 >nul
cd /d "%~dp0"
call venv\Scripts\activate.bat 2>nul || call .venv\Scripts\activate.bat 2>nul

echo.
echo  رابط عام عبر ngrok
echo  ==================
echo  1) ثبّت ngrok من: https://ngrok.com/download
echo  2) سجّل حساباً مجانياً وانسخ authtoken من لوحة التحكم
echo  3) نفّذ مرة واحدة:  ngrok config add-authtoken YOUR_TOKEN
echo.
echo  يُشغّل الخادم محلياً ثم نفق ngrok على المنفذ 8000
echo.

start "Amal Server" cmd /k "cd /d %~dp0 && call venv\Scripts\activate.bat 2>nul && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

timeout /t 4 /nobreak >nul

where ngrok >nul 2>&1
if errorlevel 1 (
  echo  ngrok غير مثبت أو غير موجود في PATH.
  echo  ثبّته ثم أعد تشغيل هذا الملف، أو نفّذ يدوياً:  ngrok http 8000
  pause
  exit /b 1
)

echo.
echo  انسخ الرابط الذي يظهر تحت Forwarding مثل: https://xxxx.ngrok-free.app
echo.
ngrok http 8000
