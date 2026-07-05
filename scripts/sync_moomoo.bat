@echo off
setlocal
cd /d "%~dp0.."
echo. >> data\moomoo_sync.log
echo ===== %date% %time% ===== >> data\moomoo_sync.log
python scripts\sync_moomoo_portfolio.py >> data\moomoo_sync.log 2>&1
endlocal
