# 企业知识库智能问答系统（RAG + Agent）

面向**企业管理制度与业务数据**场景的智能问答系统。提供「经典 RAG 检索问答」与「智能体工具调用问答」两种模式：既能基于上传的制度文档作答，也能自主调用工具查询业务数据库、执行精确计算，并以**流式**方式输出答案。

> 🌐 在线体验：<https://enterprise-rag-qa.app.workbuddy.host/>
>
> 📦 代码仓库：<https://github.com/Life-Delight/RAG-Studio>

---

## 1. 核心特性

### 1.1 双问答模式

| 模式 | 工作方式 | 适用问题 |
| --- | --- | --- |
| **经典 RAG** | 混合检索（向量 + BM25 + RRF 融合）→ 注入提示词 → 生成答案 | 制度、流程、规定类问题 |
| **智能体（Agent）** | 模型自主决策调用工具，可多轮迭代（最多 6 轮），工具结果回灌后作答 | 需要查数据、算账、多步推理的问题 |

### 1.2 智能体工具集

| 工具 | 能力 | 示例问题 |
| --- | --- | --- |
| `search_knowledge_base` | 混合检索知识库文档 | 年假有多少天？ |
| `query_business_data` | 只读 SQL 查询（员工 / 请假 / 报销三张表）。仅允许 `SELECT`，语法校验 + SQLite 只读连接双保险 | 待审核的报销有几笔？ |
| `calculate` | AST 白名单安全计算器（四则运算、幂、取模、括号） | 3 晚住宿 + 4 天餐补共多少钱？ |
| `get_current_date` | 提供时间基准 | 报销时限最晚到哪天？ |

### 1.3 知识边界与防幻觉

系统对"回答依据"有明确约束：

- **企业范围问题**（公司人员、制度、业务数据）：回答中的事实必须来自工具返回结果，查不到就如实说明，**禁止编造**
- **通用问题**（游戏、影视、闲聊、写作等）：需先检索知识库确认其中没有相关内容，才允许使用通用知识作答，且**必须标注**「以下为通用知识，不来自企业知识库」
- 知识库中已有答案的问题**不会**被标注为通用知识——判断范围以知识库内容为准，而不是看话题是否与公司业务相关
- 禁止罗列与问题无关的数据（例如把全部员工名单列一遍），也禁止在回答中暴露内部查询过程

### 1.4 流式输出与稳定性

- **真流式**：后端通过 SSE 逐 token 推送（实测单次回答 180~500 个数据块）
- **阶段状态可视化**：正在检索 / 已检索到 N 段相关内容 / 正在调用某工具 / 正在生成回答
- **官网同款输出节奏**：前端按约 45 字/秒平滑铺开（超长回答最长约 12 秒播完），避免模型生成过快造成"文字一次性蹦出"的观感
- **不会卡死**：模型调用 45 秒空闲超时保护 + 前端 25 秒断流看门狗；异常时保留已生成内容并给出明确提示
- **页面更新即时生效**：`index.html` 禁用缓存，带哈希的静态资源长期缓存

### 1.5 知识库与文档处理

- **多格式支持**：`.txt` `.md` `.pdf` `.docx` `.doc` `.csv`（旧版 `.doc` 经 LibreOffice 转换；扫描版 PDF 走 OCR 兜底）
- **批量上传**：一次选择多个文件；后台异步处理，前端展示进度与状态
- **检索范围可控**：可在问答时限定到一个或多个文档
- 处理流程：文本抽取 → 切分（默认 500 字 / 重叠 50 字）→ 向量化 → 存入 ChromaDB

---

## 2. 技术栈

| 层次 | 技术选型 |
| --- | --- |
| 后端框架 | FastAPI 0.111 · Uvicorn · Pydantic v2 |
| 大模型 | DeepSeek（OpenAI 兼容接口，通过 `openai` SDK 调用），可替换为任意 OpenAI 兼容服务 |
| 向量检索 | ChromaDB · sentence-transformers（默认 `paraphrase-multilingual-MiniLM-L12-v2`，也可换 `bge-small-zh`） |
| 关键词检索 | jieba 分词 + rank_bm25 + RRF 融合 |
| 数据存储 | SQLite（SQLAlchemy 2.0）；知识库原始文件存本地目录 |
| 文档解析 | pdfplumber · python-docx · pytesseract / pdf2image（OCR） |
| 前端 | Vue 3.4 · TypeScript · Vite 5 · Element Plus · Pinia · Vue Router · KaTeX |
| 通信 | REST + SSE（`text/event-stream`） |

---

## 3. 项目结构

```text
RAG-Studio/
├── backend/
│   ├── app/
│   │   ├── main.py                  # 应用入口：路由注册、静态托管、启动预热
│   │   ├── api/
│   │   │   ├── knowledge_base.py    # 知识库 / 文档接口
│   │   │   └── chat.py              # 会话 / 问答接口（SSE 流式 + 自检端点）
│   │   ├── core/config.py           # 配置（全部来自环境变量）
│   │   ├── models/database.py       # ORM 模型 + 业务演示数据种子
│   │   └── services/
│   │       ├── agent_service.py     # 智能体：工具定义 + Function Calling 循环
│   │       ├── llm_service.py       # 大模型调用与提示词组装
│   │       ├── embedding_service.py # 向量化（sentence-transformers / ONNX）
│   │       ├── vector_service.py    # ChromaDB 封装
│   │       ├── bm25_service.py      # 关键词检索
│   │       ├── hybrid_search_service.py  # 混合检索 + RRF 融合
│   │       └── document_service.py  # 文档解析、切分、入库
│   ├── evaluation/                  # 检索 / 问答效果评估脚本与数据集
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── views/Chat.vue            # 问答页（双模式开关、流式渲染、自检面板）
│       ├── views/KnowledgeBase.vue   # 知识库管理
│       ├── views/KnowledgeBaseDetail.vue  # 知识库详情与文档上传
│       └── api/index.ts              # 接口封装
├── 示例文档/                         # 可直接用于体验的示例制度文档
├── start_backend.bat / start_frontend.bat   # Windows 一键启动
├── stream_diag.py                    # 流式时序诊断脚本
├── verify_rag_prompt.py              # 验证"检索结果是否注入提示词"
├── verify_agent_feedback.py          # 验证"工具结果是否回灌给模型"
└── test_repeat_question.py           # 连续追问一致性测试
```

> `models/`（向量模型）、`frontend/node_modules/`、`.venv/` 以及运行期数据目录（`backend/database`、`chroma_data`、`uploaded_files`）均未纳入版本库，克隆后按第 4 节说明准备即可。

---

## 4. 快速开始

### 4.1 前置条件

- Python 3.10+（本机验证版本 3.13）
- Node.js 18+
- 一个 DeepSeek API Key（<https://platform.deepseek.com> 申请，也可换成任意 OpenAI 兼容服务）

### 4.2 启动后端

**第 1 步：配置密钥（必须）**

```bash
copy .env.example .env       # Windows；Linux/macOS 用 cp .env.example .env
# 编辑 .env，把 LLM_API_KEY 换成你自己的 DeepSeek Key
```

**第 2 步：启动（Windows 一键，推荐）**

```bash
start_backend.bat
```

该脚本会自动完成：检测并创建虚拟环境 → 安装 `backend/requirements.txt` 中的依赖（首次运行需几分钟）→ 读取 `.env` → 启动服务。**不需要手动 `pip install`。**

**或者手动执行（任意系统）**

```bash
python -m venv .venv
.venv/Scripts/activate                  # Windows；Linux/macOS 用 source .venv/bin/activate
pip install -r backend/requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

### 4.3 启动前端

```bash
cd frontend
npm install
start_frontend.bat           # 或执行 npm run dev
```

浏览器打开 <http://localhost:3000>

### 4.4 关于向量模型

向量模型体积较大，**未纳入版本库**。两种获取方式：

1. **自动下载（默认）**：不设置 `EMBED_MODEL_NAME` 时，首次运行会从 HuggingFace 自动下载默认模型；国内网络已默认配置 `HF_ENDPOINT=https://hf-mirror.com` 镜像
2. **使用本地模型**：把模型放到 `models/minilm-l12-v2/`（启动脚本检测到该目录会自动使用），或在 `.env` 中通过 `EMBED_MODEL_NAME` 指定任意本地路径 / HuggingFace 模型名

> ⚠️ `models/` 被 `.gitignore` 排除是刻意为之：不要把几百 MB 的模型提交到 Git（单文件超过 100MB 会被 GitHub 拒绝）。

### 4.5 验证是否启动成功

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","message":"RAG问答系统运行正常"}
```

首次启动会在后台预热向量模型与大模型连接，约需数十秒；该接口返回即代表服务就绪。

---

## 5. 配置说明

配置通过项目根目录的 `.env` 提供（已被 `.gitignore` 忽略，**请勿提交到仓库**）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `https://api.deepseek.com/v1` | 大模型接口地址（OpenAI 兼容） |
| `OLLAMA_MODEL` | `deepseek-chat` | 模型名 |
| `LLM_API_KEY` | — | **必填**，大模型 API Key |
| `EMBED_MODEL_NAME` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 向量模型（本地路径或 HF 模型名） |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace 镜像，便于国内下载模型 |
| `TOP_K` | `20` | 召回片段数 |
| `MIN_RELEVANCE_SCORE` | `0.55` | 相关度阈值 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `50` | 文本切分长度与重叠字数 |

---

## 6. API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET / POST | `/api/knowledge-bases` | 知识库列表 / 创建 |
| GET / PUT / DELETE | `/api/knowledge-bases/{kb_id}` | 知识库详情 / 更新 / 删除 |
| GET | `/api/knowledge-bases/{kb_id}/documents` | 文档列表（含处理状态与片段数） |
| POST | `/api/knowledge-bases/{kb_id}/documents` | 上传单个文档 |
| POST | `/api/knowledge-bases/{kb_id}/documents/batch` | 批量上传 |
| DELETE | `/api/knowledge-bases/{kb_id}/documents/{doc_id}` | 删除文档 |
| GET / POST | `/api/chat/sessions` | 会话列表 / 新建会话 |
| GET | `/api/chat/sessions/{session_id}/messages` | 会话消息（含工具调用记录） |
| POST | `/api/chat/stream` | **问答（SSE 流式）**，请求体中的 `agent_mode` 用于切换双模式 |
| GET | `/api/chat/diag-stream` | 流式自检端点（每 100ms 推一块，用于排查网络 / 代理缓冲） |

`POST /api/chat/stream` 的 SSE 事件类型：

```text
data: [META]{...}                       # 会话信息与检索来源
data: {"type":"status", ...}            # 阶段状态（检索中 / 调用工具 / 生成中）
data: {"type":"tool_call", ...}         # 智能体发起的工具调用
data: {"type":"tool_result", ...}       # 工具执行结果
data: "文本片段"                         # 回答内容（逐 token）
data: [DONE]                            # 结束
```

---

## 7. 调试与验证脚本

| 脚本 | 用途 |
| --- | --- |
| `stream_diag.py` | 记录每个数据块到达时间，判断是否真流式、是否被代理缓冲 |
| `verify_rag_prompt.py` | 用项目自身函数组装提示词并导出全文，验证检索内容确实注入了模型（导出结果见 `verify_prompt_dump.txt`） |
| `verify_agent_feedback.py` | 用录制式客户端抓取智能体的每次真实请求，验证工具结果确实回灌给模型 |
| `test_repeat_question.py` | 连续追问同一问题的场景测试（检查是否会改口或编造） |

---

## 8. 常见问题

**Q：首次启动很慢？**
A：启动时会后台预热向量模型与大模型连接；另外首次运行需下载向量模型（数百 MB），可提前按 4.4 的方式准备本地模型。

**Q：`.doc` 文件上传失败？**
A：旧版 `.doc` 依赖服务端的 LibreOffice 做格式转换，未安装时会失败，建议先另存为 `.docx`。

**Q：扫描版 PDF 解析不出内容？**
A：会走 OCR 兜底，但依赖 Tesseract 等组件；若识别效果不佳，建议先转成文本格式再上传。

**Q：回答显示"以下为通用知识，不来自企业知识库"？**
A：说明该问题在知识库中确实没有相关内容。把期望的知识上传到知识库后，即可基于文档作答。

**Q：`docker-compose.yml` 还能用吗？**
A：它是项目早期基于「本地 Ollama 模型」编写的编排文件，当前默认对接 DeepSeek 云端 API，因此以第 4 节的本地启动方式为准；如需容器化部署请自行调整该文件。

---

## 9. 说明

- 本项目为毕业设计作品，定位为**私有知识库问答系统**的实现与技术验证
- 检索效果评估方法与数据见 `HYBRID_SEARCH_AND_EVALUATION.md`
- `示例文档/` 中提供了可直接上传体验的示例制度文档
