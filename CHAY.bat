@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Thin Aptm - Tao Video Google Flow
python update.py
python thin_aptm.py
if errorlevel 1 (
  echo.
  echo *** Co loi - neu thieu thu vien chay SETUP.bat ***
  pause
)
