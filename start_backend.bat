@echo off
chcp 65001 >nul
rem ===== Start RAG-Studio backend (FastAPI, port 8000) =====
cd /d "%~dp0"

rem ---- 从 .env 读取配置（不要把密钥写进本文件，也不要提交 .env）----
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
if not defined EMBED_MODEL_NAME set "EMBED_MODEL_NAME=%~dp0models\minilm-l12-v2"

cd /d "%~dp0backend"
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
