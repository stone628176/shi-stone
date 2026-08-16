@echo off
chcp 65001 >nul
REM ========================================================
REM  一键启动本地Web服务器 + 内网穿透（手机就能访问）
REM  双击运行后：
REM   · 电脑访问：http://localhost:8088/
REM   · 手机访问：看控制台输出的公网地址（cpolar/ngrok格式）
REM ========================================================

setlocal
cd /d "%~dp0"

title 创作者工作台_新闻服务

echo.
echo ========================================================
echo   个人工作台 + 每日资讯 本地服务
echo ========================================================
echo   本地地址（电脑用）: http://localhost:8088/
echo   工作台页面:        http://localhost:8088/workbench-mobile.html
echo   新闻汇总入口:      http://localhost:8088/news_pages/index.html
echo   今日新闻页面:      http://localhost:8088/news_pages/news-%date:~0,4%-%date:~5,2%-%date:~8,2%.html
echo.
echo   关闭本窗口 = 停止服务
echo.
echo [*] 正在启动 Python 内置 HTTP 服务器 (端口 8088) ...
echo.

REM 端口 8088 绑定所有网卡（手机在同一WiFi下可以用电脑IP:8088访问）
python -m http.server 8088 --bind 0.0.0.0

pause
