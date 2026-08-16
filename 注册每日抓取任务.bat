@echo off
chcp 65001 >nul
REM ========================================================
REM  注册 Windows 计划任务 —— 每天 08:00 自动抓取资讯
REM  双击本文件运行即可（不需要管理员权限，右键"以管理员身份运行"最稳）
REM ========================================================

setlocal
cd /d "%~dp0"

set "TASKNAME=创作者工作台_每日资讯抓取"
set "SCRIPT=%~dp0news_fetcher.py"
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
REM 如果上面的路径找不到，就用系统默认的python
if not exist "%PYEXE%" set "PYEXE=python"

echo.
echo ========================================================
echo   正在注册计划任务：每天08:00自动抓取资讯
echo ========================================================
echo   任务名: %TASKNAME%
echo   Python: %PYEXE%
echo   脚本:   %SCRIPT%
echo   工作目录: %~dp0
echo.

REM 如果旧任务存在，先删
schtasks /query /tn "%TASKNAME%" >nul 2>&1
if %errorlevel%==0 (
    echo [*] 已存在同名任务，正在删除...
    schtasks /delete /tn "%TASKNAME%" /f >nul 2>&1
)

REM 创建：每天 08:00 触发，如果错过开机时间则登录后补跑一次
schtasks /create /tn "%TASKNAME%" ^
    /tr "\"%PYEXE%\" \"%SCRIPT%\"" ^
    /sc DAILY /st 08:00 ^
    /rl HIGHEST /f

if %errorlevel%==0 (
    echo.
    echo [√] 创建成功！
    echo     每天早上 08:00 会自动运行 news_fetcher.py
    echo     如果那天电脑没开机，则下次开机后会自动补跑一次。
    echo.
    echo  下面创建一个额外的"开机后30分钟补抓"任务：
    schtasks /create /tn "%TASKNAME%_开机补抓" ^
        /tr "\"%PYEXE%\" \"%SCRIPT%\"" ^
        /sc ONLOGON /delay 0030:00 ^
        /rl HIGHEST /f
    echo.
    echo [*] 测试运行一次，看看能不能正常抓...
    "%PYEXE%" "%SCRIPT%"
) else (
    echo.
    echo [X] 创建失败，请右键本文件 - 以管理员身份运行。
)

echo.
pause
