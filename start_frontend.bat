@echo off
chcp 65001 >nul
rem ===== Start RAG-Studio frontend (Vite dev server, port 3000) =====
rem 前置要求：已安装 Node.js 18+ 并在 PATH 中
cd /d "%~dp0frontend"
if not exist "node_modules" (
  echo [提示] 未检测到 node_modules，正在安装依赖...
  call npm.cmd install
)
call npm.cmd run dev
pause
