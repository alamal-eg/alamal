@echo off
chcp 65001 >nul
cd /d "%~dp0"
call venv\Scripts\activate.bat 2>nul || call .venv\Scripts\activate.bat 2>nul
echo.
echo  تشغيل على الشبكة المحلية (واي فاي / LAN)
echo  ==========================================
for /f "delims=" %%i in ('python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0]);s.close()"') do set LAN_IP=%%i
echo  من هذا الجهاز:  http://127.0.0.1:8000
echo  من جوال/جهاز آخر على نفس الشبكة:  http://%LAN_IP%:8000
echo.
echo  قد تحتاج السماح للجدار الناري بـ Python عند أول تشغيل.
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause
