# 基于 RAG 的智能问答系统

一个面向本地私有知识库场景的 RAG（Retrieval-Augmented Generation，检索增强生成）智能问答系统。项目提供知识库管理、文档上传解析、向量化检索、多轮对话、流式回答、参考来源展示、指定文档问答、公式渲染与 Docker 一键部署能力，适合作为毕业设计、课程设计或本地知识库问答原型系统使用。

> 系统默认采用本地 Ollama 大语言模型与本地 ChromaDB 向量库，知识库文件、向量数据和会话数据均保存在本地。首次拉取大模型或下载嵌入模型时可能需要网络环境。

**项目定位**：11408 考研知识场景（数学一 + 计算机 408）智能问答助手，支持数学公式渲染与知识点分点讲解。

---

## 1. 项目特性

- **本地化部署**：前端、后端、向量库、数据库与模型服务均可在本机或本地容器中运行。
- **知识库管理**：支持知识库创建、查看、编辑、删除。
- **多格式文档上传**：支持 `PDF`、`DOC`、`DOCX`、`TXT`、`MD`、`CSV`。
- **批量文档上传**：支持一次选择多个文件批量导入知识库。
- **旧版 DOC 转换**：上传 `.doc` 文件时，后端会调用 LibreOffice 转换为 `.docx` 后再解析。
- **PDF OCR 兜底**：普通文本提取为空时，可借助 OCR 对扫描版 PDF 做基础识别。
- **混合检索**：结合向量语义检索（ChromaDB）和关键词检索（BM25），使用 RRF 融合算法提升检索准确率。
- **指定文档问答**：问答时可限定在选定文档范围内检索，便于针对单个或多个文档提问。
- **多轮上下文问答**：支持结合历史对话进行追问，并对追问查询进行轻量增强。
- **流式输出**：后端通过 SSE 返回模型输出，前端可逐步展示回答内容。
- **参考来源展示**：回答可附带命中的文档来源、片段与相关度分数。
- **无上下文提示**：当知识库未检索到足够相关内容时，会提示回答基于通用知识生成。
- **Docker 一键部署**：提供 `docker-compose.yml`，可快速启动 Ollama、后端与前端服务。

---

## 2. 技术栈

| 层次 | 技术 | 说明 |
|---|---|---|
| 前端框架 | Vue 3 + TypeScript + Vite | 现代化前端开发环境 |
| UI 组件库 | Element Plus | 企业级 UI 组件 |
| 路由 | Vue Router | 前端页面切换与懒加载 |
| 状态管理 | Pinia | 轻量级状态管理 |
| HTTP 客户端 | Axios | 接口请求与 SSE 流式响应 |
| 公式渲染 | KaTeX | 数学公式 LaTeX 渲染 |
| 后端框架 | FastAPI | 高性能异步 Web 框架 |
| ORM | SQLAlchemy | 数据库访问与模型定义 |
| 数据库 | SQLite | 轻量级关系型数据库 |
| 向量库 | ChromaDB | 本地向量存储与相似度检索 |
| 嵌入模型 | sentence-transformers | 多语言文本向量编码 |
| 大语言模型 | Ollama | 本地 LLM 推理服务（OpenAI 兼容接口） |
| 文档解析 | pdfplumber、python-docx | PDF 与 Word 文档文本提取 |
| 文档转换 | LibreOffice | 旧版 DOC 转 DOCX |
| OCR 引擎 | Tesseract + Poppler | 扫描版 PDF 文字识别 |
| 容器化 | Docker / Docker Compose | 本地部署与环境封装 |

**默认模型配置**：

- 生成模型：`deepseek-r1:7b`（7B 参数，适合本地运行）
- 嵌入模型：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（多语言支持，384 维向量）

---

## 3. 核心功能

### 3.1 知识库管理

- **创建与编辑**：支持创建知识库，编辑名称与描述
- **文档统计**：实时显示文档总数、已就绪数量、知识块总数
- **级联删除**：删除知识库时自动清理关联文档、会话、消息与向量集合
- **状态监控**：实时显示知识库更新时间与文档处理状态

### 3.2 文档处理

**支持格式**：`PDF`、`DOC`、`DOCX`、`TXT`、`MD`、`CSV`

**处理流程**：

1. **文件上传**：支持单个或批量上传（多选文件）
2. **格式转换**：`.doc` 自动调用 LibreOffice 转换为 `.docx`
3. **文本提取**：
   - PDF：优先使用 pdfplumber 提取文本
   - PDF（扫描版）：文本提取为空时自动触发 Tesseract OCR
   - Word：使用 python-docx 提取段落文本
   - 纯文本：直接读取 UTF-8 编码内容
4. **文本分块**：按 `CHUNK_SIZE`（默认 500 字符）分块，重叠 `CHUNK_OVERLAP`（默认 50 字符）
5. **向量化**：使用 sentence-transformers 生成 384 维向量
6. **入库存储**：批量写入 ChromaDB 向量库
7. **状态更新**：实时更新处理进度（百分比 + 提示消息）

**文档状态**：

- `processing`：处理中（显示进度条与进度消息）
- `ready`：已就绪（可参与问答）
- `failed`：处理失败（显示错误消息）

**进度提示示例**：

- 5%：准备解析文档
- 12%：提取文本中
- 12-60%：OCR 识别中（X/Y 页）
- 65%：文本分块中
- 75%：向量化中
- 90%：写入向量库中
- 100%：处理完成

### 3.3 智能问答

**基础功能**：

- **会话管理**：新建、查看、删除对话会话
- **多轮对话**：支持结合最近 3 轮历史消息进行追问
- **流式输出**：基于 SSE 实时返回模型输出，逐字显示
- **停止回答**：支持手动中断当前生成

**高级功能**：

- **指定文档问答**：可选择一个或多个文档作为检索范围
  - 单文档知识库：自动锁定该文档
  - 多文档知识库：可手动选择目标文档
  - 适用场景：文档总结、对比分析、定向提问
  
- **文档总结模式**：自动识别总结类问题（如"总结这份文档"）
  - 优先召回同一文档的多个片段
  - 构造总结导向的 Prompt
  - 降低生成温度（0.2）提高准确性
  
- **参考来源展示**：
  - 按文档名分组展示命中片段
  - 显示相关度分数（百分比）
  - 默认展示前 5 个文档，可展开查看更多
  - 每个来源显示文本片段预览（前 200 字符）
  
- **未命中提示**：
  - 当知识库未检索到足够相关内容时显示黄色感叹号
  - 点击展开/收起提示信息
  - 提示文案："当前知识库未检索到足够相关的参考内容，以下回答基于通用知识生成，仅供参考。"

**公式渲染**：

- 使用 KaTeX 渲染数学公式
- 支持行内公式：`\( ... \)`
- 支持块级公式：`\[ ... \]`（单独成行，居中显示）
- 适合数学、物理、计算机算法等场景
- 自动识别并渲染 LaTeX 格式公式

**知识点讲解**：

- 针对"有哪些、怎么分类、需要记什么"等问题
- 自动分点概括（3-6 点）
- 每点 1-2 句话，简洁清晰
- 核心公式单独成行展示

---

## 4. 项目结构

```text
基于RAG的问答系统/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── api/                  # API 路由
│   │   │   ├── chat.py           # 会话与流式问答接口
│   │   │   └── knowledge_base.py # 知识库与文档接口
│   │   ├── core/
│   │   │   └── config.py         # 配置项与环境变量读取
│   │   ├── models/
│   │   │   └── database.py       # SQLAlchemy 数据模型
│   │   ├── services/
│   │   │   ├── document_service.py
│   │   │   ├── embedding_service.py
│   │   │   ├── llm_service.py
│   │   │   └── vector_service.py
│   │   └── main.py               # FastAPI 应用入口
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                     # Vue 前端
│   ├── src/
│   │   ├── api/                  # 前端接口封装
│   │   ├── assets/               # 样式资源
│   │   ├── router/               # 路由配置
│   │   ├── types/                # TypeScript 类型
│   │   └── views/                # 页面组件
│   │       ├── Chat.vue
│   │       ├── KnowledgeBase.vue
│   │       └── KnowledgeBaseDetail.vue
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml            # Docker 编排配置
├── README.md
├── uploaded_files/               # 上传文件目录，运行后生成
├── chroma_data/                  # ChromaDB 数据目录，运行后生成
├── database/                     # SQLite 数据目录，运行后生成
├── hf_cache/                     # Hugging Face 模型缓存目录
└── .ollama/                      # Ollama 模型数据目录
```

---

## 5. 快速启动

### 5.1 前置条件

建议安装：

- Docker Desktop
- Docker Compose
- 8GB 以上内存，推荐 16GB 及以上
- 如需 GPU 推理：
  - NVIDIA 显卡驱动
  - NVIDIA Container Toolkit

> 没有 GPU 也可以运行，但本地大模型推理速度会明显变慢。

### 5.2 Docker 一键启动

在项目根目录执行：

```bash
cd "e:\BISHE\基于RAG的问答系统"
docker-compose up -d
```

查看服务状态：

```bash
docker-compose ps
```

访问地址：

- 前端页面：`http://localhost:3000`
- 后端 API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

### 5.3 首次拉取模型

如果 Ollama 容器中还没有默认模型，可执行：

```bash
docker exec rag-ollama ollama pull deepseek-r1:7b
```

查看已有模型：

```bash
docker exec rag-ollama ollama list
```

### 5.4 重新构建

代码修改后可重建并启动：

```bash
docker-compose up -d --build
```

如需清理容器卷后重新部署：

```bash
docker-compose down -v
docker-compose up -d --build
```

> 注意：`down -v` 会删除 Docker 卷数据。当前项目主要数据通过目录挂载保存到项目目录中，但执行清理前仍建议备份重要文件。

---

## 6. 本地开发启动

如果不使用 Docker，也可以在本机分别启动 Ollama、后端和前端。

### 6.1 启动 Ollama

安装 Ollama 后，拉取默认模型：

```bash
ollama pull deepseek-r1:7b
```

确认服务可用：

```bash
ollama list
```

### 6.2 启动后端

进入后端目录：

```bash
cd "e:\BISHE\基于RAG的问答系统\backend"
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

本地开发时后端默认使用：

- Ollama 地址：`http://localhost:11434/v1`
- 数据库目录：`backend/database`
- 上传目录：`backend/uploaded_files`
- 向量库目录：`backend/chroma_data`

如果需要解析旧版 `.doc` 或扫描版 PDF，请确保本机已安装：

- LibreOffice
- Tesseract OCR
- Poppler

### 6.3 启动前端

进入前端目录：

```bash
cd "e:\BISHE\基于RAG的问答系统\frontend"
npm install
npm run dev
```

开发环境访问：

- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000/docs`

---

## 7. 使用说明

### 7.1 创建知识库

1. 打开前端页面。
2. 进入“知识库管理”。
3. 点击“新建知识库”。
4. 输入知识库名称和描述。
5. 提交后即可创建知识库。

### 7.2 上传文档

1. 进入某个知识库详情页。
2. 点击上传按钮，可选择单个或多个文档。
3. 等待后端完成解析、分块和向量化。
4. 文档状态变为 `ready` 后即可参与问答。

支持格式：

```text
.pdf / .doc / .docx / .txt / .md / .csv
```

### 7.3 发起问答

1. 打开“智能问答”页面。
2. 选择知识库。
3. 可按需选择限定问答的文档。
4. 输入问题。
5. 点击发送或使用快捷键提交。
6. 等待流式回答生成。
7. 可查看参考来源，或中途停止回答。

### 7.4 指定文档问答

当知识库中包含多个文档时，可以通过前端选择一个或多个文档后再提问。后端会将 `selected_doc_ids` 传入检索流程，使向量检索限定在选定文档范围内。

适合以下场景：

- “总结这份文档的主要内容”
- “这篇论文的研究方法是什么？”
- “只根据我选中的两个文件回答这个问题”
- “对比这两份资料的区别”

### 7.5 参考来源与未命中提示

命中知识库内容时，回答会返回参考来源，来源中包含：

- 文档名
- 命中文本片段
- 相关度分数

如果未检索到足够相关的上下文，前端会提示：

```text
当前知识库未检索到足够相关的参考内容，以下回答基于通用知识生成，仅供参考。
```

---

## 8. 配置说明

主要配置文件：

- `docker-compose.yml`
- `backend/app/core/config.py`
- `frontend/.env`
- `frontend/.env.production`
- `frontend/nginx.conf`

### 8.1 后端环境变量

`docker-compose.yml` 中后端服务默认配置：

```yaml
environment:
  - OLLAMA_BASE_URL=http://ollama:11434/v1
  - OLLAMA_MODEL=deepseek-r1:7b
  - UPLOAD_DIR=/app/uploaded_files
  - CHROMA_DIR=/app/chroma_data
  - DATABASE_DIR=/app/database
  - CHUNK_SIZE=500
  - CHUNK_OVERLAP=50
  - TOP_K=20
  - MIN_RELEVANCE_SCORE=0.55
  - HIGH_CONFIDENCE_SCORE=0.72
  - MIN_SOURCE_HITS=3
  - MIN_SOURCE_GROUPS=1
  - HF_ENDPOINT=https://hf-mirror.com
  - HF_HOME=/app/hf_cache
```

### 8.2 配置项含义

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama OpenAI 兼容接口地址 |
| `OLLAMA_MODEL` | `deepseek-r1:7b` | 问答生成模型 |
| `EMBED_MODEL_NAME` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 嵌入模型名称 |
| `UPLOAD_DIR` | `uploaded_files` | 上传文件保存目录 |
| `CHROMA_DIR` | `chroma_data` | ChromaDB 数据目录 |
| `DATABASE_DIR` | `database` | SQLite 数据目录 |
| `CHUNK_SIZE` | `500` | 文本分块大小 |
| `CHUNK_OVERLAP` | `50` | 文本分块重叠长度 |
| `TOP_K` | `20` | 初始召回候选数量 |
| `MIN_RELEVANCE_SCORE` | `0.55` | 参考来源过滤阈值 |
| `HIGH_CONFIDENCE_SCORE` | `0.72` | 高置信命中阈值 |
| `MIN_SOURCE_HITS` | `3` | 普通命中时所需最少来源数量 |
| `MIN_SOURCE_GROUPS` | `1` | 普通命中时所需最少文档组数量 |
| `CORS_ORIGINS` | `*` | 跨域允许来源，多个值用逗号分隔 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | Hugging Face 镜像地址 |
| `HF_HOME` | `/app/hf_cache` | 模型缓存目录 |

### 8.3 前端接口地址

前端接口基础地址由 `VITE_API_URL` 控制。

- Docker 部署时，前端 Nginx 会将 `/api` 代理到后端容器 `backend:8000`。
- 本地开发时，如果 `VITE_API_URL` 为空，前端会请求当前域名下的 `/api`。

---

## 9. API 概览

系统启动后访问：

```text
http://localhost:8000/docs
```

可查看 Swagger API 文档。

### 9.1 知识库接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/knowledge-bases` | 获取知识库列表 |
| `POST` | `/api/knowledge-bases` | 创建知识库 |
| `GET` | `/api/knowledge-bases/{kb_id}` | 获取知识库详情 |
| `PUT` | `/api/knowledge-bases/{kb_id}` | 更新知识库 |
| `DELETE` | `/api/knowledge-bases/{kb_id}` | 删除知识库 |

### 9.2 文档接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/knowledge-bases/{kb_id}/documents` | 获取文档列表 |
| `POST` | `/api/knowledge-bases/{kb_id}/documents` | 上传单个文档 |
| `POST` | `/api/knowledge-bases/{kb_id}/documents/batch` | 批量上传文档 |
| `DELETE` | `/api/knowledge-bases/{kb_id}/documents/{doc_id}` | 删除文档 |

### 9.3 问答接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/chat/sessions` | 获取对话列表，可传 `kb_id` 过滤 |
| `POST` | `/api/chat/sessions` | 创建对话 |
| `GET` | `/api/chat/sessions/{session_id}/messages` | 获取对话消息 |
| `DELETE` | `/api/chat/sessions/{session_id}` | 删除对话 |
| `POST` | `/api/chat/stream` | SSE 流式问答 |

`/api/chat/stream` 请求体示例：

```json
{
  "kb_id": 1,
  "session_id": 1,
  "question": "请总结这份文档的主要内容",
  "selected_doc_ids": [3]
}
```

---

## 10. 常用命令

### 10.1 Docker 服务管理

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重建并启动
docker-compose up -d --build

# 查看容器状态
docker-compose ps

# 查看全部日志
docker-compose logs -f
```

### 10.2 查看单个服务日志

```bash
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f ollama
```

### 10.3 Ollama 模型管理

```bash
# 查看模型
docker exec rag-ollama ollama list

# 拉取默认模型
docker exec rag-ollama ollama pull deepseek-r1:7b

# 简单测试模型
docker exec rag-ollama ollama run deepseek-r1:7b "你好"
```

### 10.4 后端验证

```bash
cd backend
python -m compileall app
```

### 10.5 前端验证

```bash
cd frontend
npm run build
```

---

## 11. 故障排查

### 11.1 容器启动失败

建议查看日志：

```bash
docker-compose logs -f
```

如果镜像构建异常，可尝试：

```bash
docker-compose build --no-cache
docker-compose up -d
```

### 11.2 模型不可用

检查 Ollama 容器与模型：

```bash
docker-compose logs -f ollama
docker exec rag-ollama ollama list
docker exec rag-ollama ollama pull deepseek-r1:7b
```

### 11.3 首次问答较慢

首次启动时可能出现以下耗时操作：

- 下载或加载嵌入模型
- 加载 Ollama 大语言模型
- 初始化 ChromaDB
- 首次文档向量化

等待模型加载完成后，后续响应通常会更稳定。

### 11.4 文档处理失败

建议检查：

1. 文件格式是否在支持范围内。
2. 文件是否为空、损坏或加密。
3. PDF 是否为复杂扫描件。
4. 后端日志中的错误信息。
5. `.doc` 转换依赖的 LibreOffice 是否可用。
6. OCR 依赖的 Tesseract 与 Poppler 是否可用。

Docker 后端镜像已安装：

- `libreoffice`
- `libreoffice-writer`
- `tesseract-ocr`
- `tesseract-ocr-chi-sim`
- `poppler-utils`

### 11.5 大文件上传失败

当前前端 Nginx 配置中已设置：

```nginx
client_max_body_size 100m;
```

前端 Axios 超时时间为 300 秒。如果调整了上传限制或代理配置，需重建前端容器：

```bash
docker-compose up -d --build frontend
```

### 11.6 GPU 未生效

可检查：

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
docker exec rag-ollama nvidia-smi
```

如果不使用 GPU，可根据实际环境调整或移除 `docker-compose.yml` 中 `ollama` 服务的 GPU 设备声明。

### 11.7 端口冲突

默认端口：

- 前端：`3000`
- 后端：`8000`
- Ollama：`11434`

如果端口被占用，可在 `docker-compose.yml` 中修改端口映射。

---

## 12. 数据目录说明

| 目录 | 说明 | 大小估算 | 是否可删除 |
|---|---|---|---|
| `uploaded_files/` | 用户上传的原始文件 | 取决于上传文件数量 | 否，删除后无法重新解析 |
| `chroma_data/` | ChromaDB 向量数据 | 约为文档总大小的 2-5 倍 | 可重建，但需重新处理所有文档 |
| `database/` | SQLite 数据库文件（rag.db） | 通常 < 100MB | 否，包含所有元数据和会话 |
| `hf_cache/` | sentence-transformers 模型缓存 | 约 400MB（首次下载） | 可删除，会自动重新下载 |
| `.ollama/` | Ollama 模型文件 | 4-8GB（取决于模型） | 可删除，需重新拉取模型 |

**备份建议**：

- 必须备份：`uploaded_files/`、`database/`
- 建议备份：`chroma_data/`（避免重新处理文档）
- 可选备份：`hf_cache/`、`.ollama/`（可重新下载）

**迁移步骤**：

1. 停止所有服务：`docker-compose down`
2. 打包数据目录：`tar -czf rag-backup.tar.gz uploaded_files/ chroma_data/ database/`
3. 在新环境解压：`tar -xzf rag-backup.tar.gz`
4. 重新启动服务：`docker-compose up -d`
5. 等待模型加载完成

**清理建议**：

```bash
# 清理失败的文档（保留数据库记录）
# 手动删除 uploaded_files/ 中对应的文件

# 完全重置（删除所有数据）
docker-compose down -v
rm -rf uploaded_files/ chroma_data/ database/ hf_cache/ .ollama/
docker-compose up -d
```

---

## 13. 功能边界与技术特点

### 13.1 已实现功能

**核心功能**：
- ✅ 本地知识库问答（无需联网，数据私有）
- ✅ 多格式文档解析（PDF、DOC、DOCX、TXT、MD、CSV）
- ✅ 批量文档上传（多选文件一次提交）
- ✅ 旧版 DOC 自动转换（LibreOffice 转换）
- ✅ PDF OCR 兜底（Tesseract 扫描版识别）
- ✅ 文档分块与向量化（可配置分块大小与重叠）
- ✅ 向量语义检索（ChromaDB 相似度检索）
- ✅ 指定文档问答（限定检索范围）
- ✅ 多轮上下文问答（结合历史对话）
- ✅ SSE 流式输出（逐字显示回答）
- ✅ 手动停止回答（中断生成）
- ✅ 参考来源展示（文档名、片段、分数）
- ✅ 未命中提示（知识库无相关内容时提示）
- ✅ 公式渲染（KaTeX 数学公式）
- ✅ 知识点分点讲解（适合考研场景）
- ✅ Docker 一键部署（容器化环境）

**技术特点**：
- ✅ 异步处理（FastAPI 异步框架）
- ✅ 实时进度（文档处理进度百分比）
- ✅ 会话管理（多会话切换与删除）
- ✅ 级联删除（删除知识库时清理关联数据）
- ✅ 错误处理（文档处理失败时显示错误信息）
- ✅ 跨域支持（CORS 配置）
- ✅ 健康检查（`/health` 端点）

### 13.2 暂未实现功能

**用户系统**：
- ❌ 用户登录与注册
- ❌ 角色权限管理
- ❌ 知识库访问控制
- ❌ 多用户协作

**高级检索**：
- ❌ 混合检索（BM25 + 向量）
- ❌ 文档重排（reranker 模型）
- ❌ 查询改写（query rewriting）
- ❌ 联网搜索增强

**文档处理**：
- ❌ Excel / XLSX 表格解析
- ❌ PPT / PPTX 演示文稿解析
- ❌ 网页爬取与解析
- ❌ 高精度版面还原式 OCR
- ❌ 图片内容理解（多模态）

**功能增强**：
- ❌ 对话导出（Markdown / PDF）
- ❌ 文档摘要生成
- ❌ 问答质量评价
- ❌ 知识图谱构建
- ❌ 后台任务队列（Celery / RQ）

### 13.3 技术限制

**模型限制**：
- 生成模型：7B 参数，适合本地运行，但能力不如大型商业模型
- 嵌入模型：384 维向量，检索精度有限
- 上下文长度：受模型限制，长文档可能截断

**性能限制**：
- CPU 推理速度较慢（建议使用 GPU）
- 大文件处理耗时（50 页 PDF 约 1-3 分钟）
- OCR 识别速度慢（扫描版 PDF 约 10-30 秒/页）
- 并发处理能力有限（单机部署）

**功能限制**：
- 仅支持文本内容（不支持图片、表格理解）
- 不支持实时更新（文档修改需重新上传）
- 不支持版本管理（文档覆盖无历史记录）
- 不支持细粒度权限（无文档级权限控制）

---

## 14. 后续优化方向

### 14.1 短期优化（1-2 周）

**性能优化**：
- 引入后台任务队列（Celery），提升大批量文档处理稳定性
- 优化向量检索性能（批量查询、缓存）
- 增加文档处理并发数（多进程/多线程）

**功能完善**：
- 支持 Excel / XLSX 表格解析
- 增加对话导出功能（Markdown / JSON）
- 增加文档预览功能（PDF / 图片）
- 优化错误提示（更友好的错误信息）

### 14.2 中期优化（1-2 月）

**检索增强**：
- 引入 BM25 + 向量的混合检索策略
- 增加 reranker 模型，提高召回片段排序质量
- 支持查询改写（query rewriting）
- 增加检索结果缓存

**文档处理**：
- 支持 PPT / PPTX 演示文稿解析
- 增强 OCR 能力（版面分析、表格识别）
- 支持网页爬取与解析
- 增加文档去重功能

### 14.3 长期优化（3-6 月）

**用户系统**：
- 增加用户认证与注册
- 实现角色权限管理（管理员、普通用户）
- 支持知识库访问控制（公开、私有、共享）
- 增加多用户协作功能

**高级功能**：
- 引入多模态模型（图片理解）
- 构建知识图谱（实体关系抽取）
- 增加问答质量评价（用户反馈）
- 支持联网搜索增强（实时信息）

**部署优化**：
- 支持分布式部署（多机负载均衡）
- 增加监控告警（Prometheus + Grafana）
- 优化容器镜像大小（多阶段构建）
- 增加自动化测试（单元测试、集成测试）

---

## 15. 使用场景示例

### 15.1 考研复习场景

**场景描述**：考研学生上传数学、计算机专业课资料，进行知识点查询与总结。

**操作流程**：

1. 创建知识库："数学一-高等数学"
2. 上传资料：教材 PDF、笔记 Word、真题 PDF
3. 等待处理完成（约 5-10 分钟）
4. 开始提问：
   - "泰勒展开式的定义是什么？"
   - "拉格朗日中值定理有哪些应用？"
   - "总结这份真题的考点分布"

**预期效果**：

- 快速查找知识点定义
- 公式自动渲染，清晰美观
- 分点总结，便于记忆
- 参考来源可追溯原文

### 15.2 论文阅读场景

**场景描述**：研究生阅读多篇论文，进行文献综述与对比分析。

**操作流程**：

1. 创建知识库："深度学习-注意力机制"
2. 上传论文：Transformer、BERT、GPT 等论文 PDF
3. 指定文档提问：
   - 选择 Transformer 论文："这篇论文的核心创新是什么？"
   - 选择 BERT 论文："BERT 的预训练任务有哪些？"
   - 选择多篇论文："对比这三篇论文的注意力机制设计"

**预期效果**：

- 快速理解论文核心思想
- 对比不同论文的异同点
- 提取关键技术细节
- 辅助撰写文献综述

### 15.3 技术文档查询场景

**场景描述**：开发人员上传项目文档、API 文档，进行快速查询。

**操作流程**：

1. 创建知识库："项目文档-后端 API"
2. 上传文档：接口文档、设计文档、部署文档
3. 快速查询：
   - "用户登录接口的请求参数有哪些？"
   - "如何部署到生产环境？"
   - "数据库表结构是怎样的？"

**预期效果**：

- 快速查找接口定义
- 减少翻阅文档时间
- 提高开发效率
- 新人快速上手

---

## 16. 常见问题 FAQ

### Q1: 为什么首次启动很慢？

**A**: 首次启动需要：
- 下载嵌入模型（约 400MB）
- 拉取 Ollama 模型（约 4-8GB）
- 初始化数据库与向量库

建议提前拉取模型：

```bash
docker exec rag-ollama ollama pull deepseek-r1:7b
```

### Q2: 为什么文档处理失败？

**A**: 常见原因：
- 文件格式不支持（检查是否为 PDF、DOC、DOCX、TXT、MD、CSV）
- 文件损坏或加密（尝试重新下载或解密）
- PDF 为复杂扫描件（OCR 识别失败）
- 文件过大（建议拆分为多个小文件）

查看后端日志获取详细错误信息：

```bash
docker-compose logs -f backend
```

### Q3: 为什么回答不准确？

**A**: 可能原因：
- 知识库未包含相关内容（上传更多相关文档）
- 检索阈值过高（降低 `MIN_RELEVANCE_SCORE`）
- 问题表述不清晰（换一种问法）
- 模型能力限制（考虑使用更大的模型）

优化建议：
- 上传高质量、结构化的文档
- 使用明确、具体的问题
- 指定文档范围提问
- 调整检索参数

### Q4: 如何更换模型？

**A**: 修改 `docker-compose.yml` 中的 `OLLAMA_MODEL` 环境变量：

```yaml
environment:
  - OLLAMA_MODEL=qwen2.5:7b  # 更换为其他模型
```

然后拉取新模型并重启：

```bash
docker exec rag-ollama ollama pull qwen2.5:7b
docker-compose restart backend
```

### Q5: 如何调整检索参数？

**A**: 修改 `docker-compose.yml` 中的检索参数：

```yaml
environment:
  - TOP_K=20                    # 初始召回数量（默认 20）
  - MIN_RELEVANCE_SCORE=0.55    # 最低相关度（默认 0.55）
  - CHUNK_SIZE=500              # 分块大小（默认 500）
  - CHUNK_OVERLAP=50            # 分块重叠（默认 50）
```

重启后端生效：

```bash
docker-compose restart backend
```

### Q6: 如何备份数据？

**A**: 备份关键目录：

```bash
# 停止服务
docker-compose down

# 打包数据
tar -czf rag-backup-$(date +%Y%m%d).tar.gz \
  uploaded_files/ \
  chroma_data/ \
  database/

# 重新启动
docker-compose up -d
```

### Q7: 如何清理数据？

**A**: 根据需求选择清理方式：

```bash
# 仅清理失败的文档（手动删除 uploaded_files/ 中的文件）

# 清理某个知识库（通过前端删除）

# 完全重置（删除所有数据）
docker-compose down -v
rm -rf uploaded_files/ chroma_data/ database/
docker-compose up -d
```

---

## 17. 项目状态与许可

### 17.1 项目信息

- **项目名称**：基于 RAG 的智能问答系统
- **当前版本**：1.0.0
- **开发状态**：可运行 / 可演示 / 适合毕业设计与课程设计
- **适用场景**：考研复习、论文阅读、技术文档查询、知识管理
- **技术栈**：Vue 3 + FastAPI + ChromaDB + Ollama

### 17.2 系统要求

**最低配置**：
- CPU：4 核心
- 内存：8GB
- 硬盘：20GB 可用空间
- 操作系统：Windows 10+ / macOS 10.15+ / Linux

**推荐配置**：
- CPU：8 核心
- 内存：16GB
- 硬盘：50GB 可用空间（含模型）
- GPU：NVIDIA GPU（6GB+ 显存）
- 操作系统：Ubuntu 20.04+ / Windows 11

### 17.3 性能参考

**文档处理速度**（CPU 模式）：
- 10 页 PDF（文字版）：10-30 秒
- 10 页 PDF（扫描版）：1-3 分钟
- 50 页 Word 文档：20-60 秒
- 100KB 文本文件：5-15 秒

**问答响应速度**（CPU 模式）：
- 首次问答：5-15 秒（含模型加载）
- 后续问答：2-8 秒
- 流式输出：逐字显示，约 10-30 字/秒

**GPU 加速效果**：
- 问答速度提升：3-5 倍
- 文档处理提升：1.5-2 倍

### 17.4 贡献指南

欢迎提交 Issue 和 Pull Request。

**开发环境搭建**：

```bash
# 克隆项目
git clone <repository-url>
cd 基于RAG的问答系统

# 启动开发环境
docker-compose up -d

# 或本地开发
cd backend && pip install -r requirements.txt
cd frontend && npm install
```

**代码规范**：
- Python：遵循 PEP 8
- TypeScript：遵循 ESLint 规则
- 提交信息：使用语义化提交（Conventional Commits）

### 17.5 致谢

本项目使用了以下开源项目：

- [Vue.js](https://vuejs.org/) - 前端框架
- [FastAPI](https://fastapi.tiangolo.com/) - 后端框架
- [ChromaDB](https://www.trychroma.com/) - 向量数据库
- [Ollama](https://ollama.ai/) - 本地 LLM 服务
- [sentence-transformers](https://www.sbert.net/) - 文本嵌入模型
- [Element Plus](https://element-plus.org/) - UI 组件库
- [KaTeX](https://katex.org/) - 数学公式渲染

---

## 18. 联系方式

如有问题或建议，欢迎通过以下方式联系：

- 项目地址：`e:\BISHE\基于RAG的问答系统`
- 文档版本：v1.0.0
- 最后更新：2026-05-19

**技术支持**：

- 查看项目文档：本 README 文件
- 查看 API 文档：`http://localhost:8000/docs`
- 查看后端日志：`docker-compose logs -f backend`
- 查看前端日志：`docker-compose logs -f frontend`

---

**祝使用愉快！**
