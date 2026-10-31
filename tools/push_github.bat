@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo ============================================
echo   推送 Strelitzia HID Battery 到 GitHub
echo   目标: https://github.com/StrelitziaZYN/HID-Battery
echo ============================================
echo.

git remote remove origin >nul 2>&1
git remote add origin https://github.com/StrelitziaZYN/HID-Battery.git

echo [1/4] 拉取远端...
git fetch origin main
if errorlevel 1 goto fail

echo.
echo [2/4] 合并远端初始提交（LICENSE，与本地历史无关）...
git rev-parse --verify origin/main >nul 2>&1
if errorlevel 1 (
    echo      远端还没有 main 分支，跳过合并
) else (
    git merge-base HEAD origin/main >nul 2>&1
    if errorlevel 1 (
        git merge --allow-unrelated-histories --no-rebase origin/main -m "chore: 合并远端初始提交（LICENSE）"
        if errorlevel 1 goto conflict
    ) else (
        echo      已有共同历史，无需合并
    )
)

echo.
echo [3/4] 推送（首次会弹出浏览器登录 GitHub）...
git push -u origin main
if errorlevel 1 goto fail

echo.
echo [4/4] 校验...
git log --oneline -3
git rev-parse --short HEAD
echo.
echo 完成。稍后访问 https://github.com/StrelitziaZYN/HID-Battery 查看。
pause
exit /b 0

:conflict
echo.
echo [x] 合并有冲突，请把上面的冲突文件列表发给助手处理。
pause
exit /b 1

:fail
echo.
echo [x] 失败。常见原因：没有登录 GitHub，或网络不通。
echo     可先在命令行执行一次 git push，按提示完成浏览器登录后重试本脚本。
pause
exit /b 1
