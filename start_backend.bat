@echo off
chcp 65001 >nul
rem ===== Start RAG-Studio backend (FastAPI, port 8000) =====
rem 首次运行会自动创建虚拟环境并安装依赖，无需手动 pip install
cd /d "%~dp0"

rem ---- 1) 依赖自检：虚拟环境缺失则自动创建并安装 requirements ----
if not exist ".venv\Scripts\python.exe" (
  echo [初始化] 未检测到虚拟环境，开始创建并安装依赖（首次约需几分钟）...
  python -m venv .venv
  if errorlevel 1 (
    echo [错误] 创建虚拟环境失败：请先安装 Python 3.10+ 并确保 python 命令在 PATH 中。
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
  ".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
  if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重新运行本脚本。
    pause
    exit /b 1
  )
  echo [初始化] 依赖安装完成。
)

rem ---- 2) 配置自检：.env 必须存在（不要把密钥写进本文件，也不要提交 .env）----
if not exist ".env" (
  echo [错误] 未找到 .env 配置文件。
  echo        请将 .env.example 复制为 .env，并把 LLM_API_KEY 换成你自己的 DeepSeek API Key。
  echo        申请地址: https://platform.deepseek.com
  pause
  exit /b 1
)
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

if not defined OLLAMA_BASE_URL set "OLLAMA_BASE_URL=https://api.deepseek.com/v1"
if not defined OLLAMA_MODEL set "OLLAMA_MODEL=deepseek-chat"
if not defined HF_ENDPOINT set "HF_ENDPOINT=https://hf-mirror.com"
rem 本地已有向量模型则用本地目录，否则留空由代码默认值从 HuggingFace 下载（首次会自动下载）
if not defined EMBED_MODEL_NAME (
  if exist "%~dp0models\minilm-l12-v2" set "EMBED_MODEL_NAME=%~dp0models\minilm-l12-v2"
)

rem ---- 3) 启动服务 ----
cd /d "%~dp0backend"
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
