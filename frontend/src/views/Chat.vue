<template>
  <div class="chat-layout">
    <div class="sessions-panel">
      <div class="sessions-header">
        <span>对话历史</span>
        <el-button text size="small" @click="handleKbSelectorClick">
          <el-icon><Plus /></el-icon>
        </el-button>
      </div>

      <div class="kb-selector" v-if="selectedKb" @click="handleKbSelectorClick">
        <el-icon><Collection /></el-icon>
        <span class="kb-sel-name">{{ selectedKb.name }}</span>
        <el-icon class="switch-icon"><Switch /></el-icon>
      </div>
      <div class="kb-selector empty" v-else @click="handleKbSelectorClick">
        <el-icon><FolderAdd /></el-icon>
        <span>选择知识库</span>
      </div>

      <el-button class="new-chat-btn" @click="newSession" v-if="selectedKb" size="small">
        <el-icon><EditPen /></el-icon> 新对话
      </el-button>

      <div class="session-list">
        <div
          v-for="s in sessions" :key="s.id"
          class="session-item"
          :class="{ active: currentSessionId === s.id }"
          @click="loadSession(s.id)"
        >
          <el-icon><ChatLineRound /></el-icon>
          <span class="session-title">{{ s.title }}</span>
          <span v-if="sessionStatus(s.id)" class="session-status-dot" :class="sessionStatus(s.id)"></span>
          <el-button text size="small" class="del-btn" @click.stop="deleteSession(s.id)" :disabled="processingSessionId === s.id">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
        <div class="empty-sessions" v-if="sessions.length === 0 && selectedKb">暂无对话</div>
      </div>
    </div>

    <div class="chat-main">
      <div class="chat-header">
        <h2>{{ selectedKb ? selectedKb.name + ' · 智能问答' : '智能问答' }}</h2>
        <div v-if="selectedKb" class="agent-mode-wrap" title="智能体模式：AI 可自主调用知识库检索、业务数据查询、计算器等工具">
          <span class="agent-mode-label">智能体模式</span>
          <el-switch v-model="agentMode" :disabled="isStreaming" />
        </div>
        <div v-if="selectedKb" class="doc-picker-wrap">
          <div class="doc-picker-label">检索范围</div>
          <el-select
            v-model="selectedDocIds"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
            filterable
            :disabled="readyDocuments().length <= 1 || isStreaming"
            placeholder="全部已就绪文档"
            class="doc-picker"
          >
            <el-option
              v-for="doc in readyDocuments()"
              :key="doc.id"
              :label="doc.original_name"
              :value="doc.id"
            />
          </el-select>
        </div>
      </div>

      <div class="chat-welcome" v-if="messages.length === 0">
        <div class="welcome-icon">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#06b6d4" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h3>RAG 智能问答系统</h3>
        <p>{{ welcomeSubtitle }}</p>
        <div class="welcome-tips" v-if="selectedKb">
          <div class="tip" v-for="t in currentTips" :key="t" @click="quickQuestion(t)">{{ t }}</div>
        </div>
        <div v-if="selectedKb && readyDocuments().length" class="welcome-doc-hint">
          <span v-if="readyDocuments().length === 1">当前知识库只有 1 个文件，提问时会自动锁定该文件。</span>
          <span v-else-if="selectedDocIds.length">当前已指定 {{ selectedDocIds.length }} 个文件作为检索范围。</span>
          <span v-else>当前默认检索整个知识库，你也可以在顶部指定一个或多个文件。</span>
        </div>
      </div>

      <div class="messages-area" ref="msgArea" v-show="messages.length > 0">
        <div v-for="(msg, idx) in messages" :key="idx" class="message-row" :class="msg.role">
          <div class="avatar">
            <el-icon v-if="msg.role === 'user'"><UserFilled /></el-icon>
            <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <div class="bubble-wrap">
            <div class="bubble" :class="msg.role">
              <div v-if="showStatusRow(msg)" class="stream-status">
                <span class="status-loader"></span>
                <span class="status-text">{{ msg.statusText }}</span>
                <span class="status-elapsed" v-if="msg.elapsed">{{ msg.elapsed }}s</span>
              </div>
              <div v-if="msg.isStreaming" class="assistant-rich streaming-plain">{{ displayMessageContent(msg) }}</div><span v-if="msg.isStreaming && !showStatusRow(msg)" class="cursor-blink">|</span>
              <div v-if="msg.isStreaming && (msg.content || '').trim()" class="reveal-line">
                <span class="status-loader"></span>输出中 · {{ msg.revealedSeconds || '0.0' }}s
              </div>
              <div v-else-if="msg.content && msg.role === 'assistant'" class="assistant-rich" v-html="renderAssistantHtml(displayMessageContent(msg))"></div>
              <span v-else-if="msg.content" style="white-space: pre-wrap;">{{ displayMessageContent(msg) }}</span>
              <div v-else-if="msg.role === 'assistant'" class="thinking">
                <span class="dot-pulse"></span><span class="dot-pulse"></span><span class="dot-pulse"></span>
              </div>
            </div>
            <div v-if="showNoContextBanner(msg)" class="no-context-inline">
              <button class="no-context-toggle" type="button" @click="toggleNoticeExpand(idx)" :title="isNoticeExpanded(idx) ? '收起提示' : '展开提示'">
                <el-icon><WarningFilled /></el-icon>
              </button>
              <transition name="notice-fade">
                <div v-if="isNoticeExpanded(idx)" class="no-context-banner" @click="toggleNoticeExpand(idx)">
                  <span>{{ noContextNotice(msg) }}</span>
                </div>
              </transition>
            </div>
          </div>
        </div>
      </div>

      <div class="input-area">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="3"
          :placeholder="selectedKb ? '输入问题，按 Ctrl+Enter 发送...' : '请先从左侧选择知识库'"
          :disabled="!selectedKb || isStreaming"
          @keydown.ctrl.enter="sendMessage"
          resize="none"
        />
        <div class="input-actions">
          <div class="speed-wrap">
            <span class="build-tag" :title="'前端构建版本：' + APP_BUILD">{{ APP_BUILD }}</span>
            <el-button text size="small" class="diag-btn" @click="openDiag">流式自检</el-button>
          </div>
          <span class="hint">
            {{ readyDocuments().length === 1 ? '已自动锁定唯一文件' : (selectedDocIds.length ? `已指定 ${selectedDocIds.length} 个文件` : '未指定文件时默认检索整个知识库') }}
          </span>
          <el-button v-if="isCurrentSessionStreaming()" type="danger" plain :loading="isStopping" @click="stopStreaming">
            <el-icon><Close /></el-icon> 停止回答
          </el-button>
          <el-button v-else type="primary" :disabled="!selectedKb || !inputText.trim() || isStreaming" @click="sendMessage">
            <el-icon><Promotion /></el-icon> 发送
          </el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="showDiag" title="流式输出自检" width="640px">
      <div class="diag-body">
        <el-button type="primary" size="small" :loading="diagRunning" @click="runStreamDiag">
          {{ diagRunning ? '自检中（约 3 秒）…' : '开始自检' }}
        </el-button>
        <pre class="diag-log">{{ diagLines.join('\n') }}</pre>
      </div>
    </el-dialog>

    <el-dialog v-model="showKbSelect" title="选择知识库" width="460px">
      <div class="kb-list">
        <div v-for="kb in allKbs" :key="kb.id" class="kb-option" :class="{ active: selectedKb?.id === kb.id }" @click="selectKb(kb)">
          <el-icon><Collection /></el-icon>
          <div>
            <div class="kb-opt-name">{{ kb.name }}</div>
            <div class="kb-opt-desc">{{ kb.document_count }} 个文档</div>
          </div>
        </div>
        <el-empty v-if="allKbs.length === 0" description="暂无知识库，请先创建" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatLineRound, Close, Collection, Document, EditPen, FolderAdd, Plus, Promotion, Switch, UserFilled, WarningFilled } from '@element-plus/icons-vue'
import { kbApi, chatApi } from '@/api'
import type { KnowledgeBase, ChatSession, Source, Document as KbDocument } from '@/types'

type ChatRequestPayload = {
  question: string
  session_id?: number
  kb_id: number
  selected_doc_ids?: number[]
  agent_mode?: boolean
}

type AgentToolStep = {
  name: string
  arguments: string
  result: string
  status: 'running' | 'done'
}

const route = useRoute()
const msgArea = ref<HTMLElement | null>(null)
const inputText = ref('')
const isStreaming = ref(false)
const isStopping = ref(false)
const processingSessionId = ref<number | null>(null)
const readySessionId = ref<number | null>(null)
let readyStatusTimer: number | null = null
let currentAbortController: AbortController | null = null
const showKbSelect = ref(false)
const allKbs = ref<KnowledgeBase[]>([])
const selectedKb = ref<KnowledgeBase | null>(null)
const sessions = ref<ChatSession[]>([])
const currentSessionId = ref<number | null>(null)
const messages = ref<any[]>([])
const documents = ref<KbDocument[]>([])
const selectedDocIds = ref<number[]>([])
const activeStreamingSessionId = ref<number | null>(null)
const activeStreamingMessage = ref<any | null>(null)
const expandedSourceMap = ref<Record<number, boolean>>({})
const expandedNoticeMap = ref<Record<number, boolean>>({})

const classicTips = ['请总结这份文档的主要内容', '文档中提到了哪些关键概念？', '有哪些重要的结论或建议？']
const agentTips = [
  '研发部有多少名员工？',
  '张伟今年一共休了多少天假？',
  '待审核的报销单有几笔？金额合计多少？',
  '普通员工一线城市出差的住宿标准和餐补是多少？'
]
const NO_CONTEXT_NOTICE = '当前知识库未检索到足够相关的参考内容，以下回答基于通用知识生成，仅供参考。'

const agentMode = ref(localStorage.getItem('rag_agent_mode') === '1')
watch(agentMode, (val) => localStorage.setItem('rag_agent_mode', val ? '1' : '0'))

// 回答输出节奏：固定 45 字/秒（与豆包 / DeepSeek 官网观感一致）
// 背景：本后端用的模型原生生成速度约 110~220 字/秒，比官网观感快 3~5 倍，
// 因此需要在前端按官网节奏消费 token，才能呈现"逐字流出"的效果。
const REVEAL_RATE = 45
// 长回答限时：整段最长约 12 秒播完，避免超长回答等太久
const REVEAL_MAX_SECONDS = 12
// DOM 更新节流：文本按 20ms 计时推进，但重绘最多每 80ms 一次（避免高频重排导致卡顿）
const REVEAL_RENDER_MS = 80

// 构建版本标记：界面上可见，用于确认浏览器加载的是不是最新前端
const APP_BUILD = 'v8 · 纯净回答'

// ---------- 流式自检（在用户自己的浏览器里实测）----------
const showDiag = ref(false)
const diagRunning = ref(false)
const diagLines = ref<string[]>([])

function openDiag() {
  showDiag.value = true
  diagLines.value = [
    `构建版本: ${APP_BUILD}`,
    `输出节奏: ${REVEAL_RATE} 字/秒（与豆包/DeepSeek 官网一致）`,
    '',
    '点击「开始自检」：会在当前浏览器里真实请求一次服务端流式端点，',
    '并检测逐字输出所需的定时器是否可运行。',
  ]
}

async function runStreamDiag() {
  if (diagRunning.value) return
  diagRunning.value = true
  const lines: string[] = []
  const push = (s: string) => { lines.push(s); diagLines.value = [...lines] }

  push(`【构建版本】${APP_BUILD}`)
  push(`【输出节奏】${REVEAL_RATE} 字/秒`)
  push(`【浏览器】${navigator.userAgent}`)
  push('')

  const animOk = await new Promise<boolean>((resolve) => {
    let ticks = 0
    const timer = window.setInterval(() => { ticks += 1 }, 20)
    window.setTimeout(() => { window.clearInterval(timer); resolve(ticks >= 5) }, 200)
  })
  push(`【逐字动画能力】${animOk ? '✅ 正常（20ms 定时器可运行）' : '❌ 异常（浏览器未执行定时器，动画无法生效）'}`)
  push('')
  push('【SSE 传输自检】服务端每 100ms 推 1 块，共 30 块（应约 3 秒陆续到达）…')

  const t0 = performance.now()
  const stamps: number[] = []
  try {
    const resp = await fetch(chatApi.diagStream())
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        const dataLine = frame.split('\n').find((l) => l.startsWith('data: '))
        if (!dataLine) continue
        const payload = dataLine.slice(6)
        if (payload === '[DONE]') continue
        stamps.push(performance.now() - t0)
      }
    }
  } catch (e: any) {
    push(`❌ 自检请求失败：${e?.name || ''} ${e?.message || e}`)
  }

  const total = stamps.length
  push(`收到数据块：${total} / 30`)
  let spread = 0
  if (total > 0) {
    spread = (stamps[total - 1] - stamps[0]) / 1000
    push(`首块 ${((stamps[0]) / 1000).toFixed(2)}s ｜ 末块 ${((stamps[total - 1]) / 1000).toFixed(2)}s ｜ 跨度 ${spread.toFixed(2)}s`)
  }
  push('')
  if (total === 0) {
    push('【判定】❌ 没有收到任何数据块，请检查服务是否正常')
  } else if (spread >= 2) {
    push('【判定】✅ 传输层是逐块流式的（约 3 秒陆续到达，正常）')
  } else if (spread >= 0.5) {
    push('【判定】⚠️ 到达偏集中，中间层可能部分缓冲')
  } else {
    push('【判定】❌ 被一次性缓冲（30 块几乎同时到达）—— 代理/网关在缓冲 SSE')
  }
  if (animOk && spread >= 2) {
    push('【结论】传输与动画均正常：若仍看不到逐字效果，请确认界面左上/左下的构建版本号是否与最新一致（否则是页面没更新）')
  } else if (!animOk) {
    push('【结论】问题在浏览器端：动画定时器无法运行，需要换用真实浏览器窗口打开（部分预览面板不支持）')
  }
  diagRunning.value = false
}

const currentTips = computed(() => (agentMode.value ? agentTips : classicTips))
const welcomeSubtitle = computed(() => {
  if (!selectedKb.value) return '请从左侧选择一个知识库开始对话'
  return agentMode.value
    ? `智能体模式：基于「${selectedKb.value.name}」+ 业务数据库，AI 自主调用工具回答`
    : `基于「${selectedKb.value.name}」知识库回答问题`
})

const TOOL_DISPLAY_NAMES: Record<string, string> = {
  search_knowledge_base: '知识库检索',
  query_business_data: '业务数据查询',
  calculate: '数学计算',
  get_current_date: '获取当前日期',
}

function toolDisplayName(name: string) {
  return TOOL_DISPLAY_NAMES[name] || name
}

function compactText(text: string, maxLen: number) {
  const normalized = (text || '').replace(/\s+/g, ' ').trim()
  return normalized.length > maxLen ? normalized.slice(0, maxLen) + '...' : normalized
}

function parseToolSteps(raw: any): AgentToolStep[] {
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw || '[]') : raw
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function showStatusRow(msg: any) {
  if (msg?.role !== 'assistant') return false
  if (!msg?.isStreaming) return false
  if (!msg?.statusText) return false
  // 回答文字开始输出后，状态行自动让位
  return !(msg.content || '').trim()
}

function handleAgentEvent(ev: any, msg: any) {
  if (ev.type === 'status') {
    msg.statusText = ev.message || ''
    msg.statusStage = ev.stage || ''
    scrollToBottom()
  } else if (ev.type === 'tool_call') {
    msg.toolSteps.push({ name: ev.name || '', arguments: ev.arguments || '', result: '', status: 'running' })
    scrollToBottom()
  } else if (ev.type === 'tool_result') {
    for (let i = msg.toolSteps.length - 1; i >= 0; i--) {
      const step = msg.toolSteps[i]
      if (step.name === ev.name && step.status === 'running') {
        step.result = ev.result || ''
        step.status = 'done'
        break
      }
    }
    scrollToBottom()
  } else if (ev.type === 'sources') {
    if (Array.isArray(ev.sources) && ev.sources.length) msg.sources = JSON.stringify(ev.sources)
  } else if (ev.type === 'content') {
    appendStreamText(msg, ev.content || '')
  }
}

// ---------- 平滑输出：把爆发式到达的文字按“字/秒”的节奏流出来 ----------
const REVEAL_TICK_MS = 20

function appendStreamText(msg: any, text: string) {
  if (!text) return
  msg.rawContent = (msg.rawContent || '') + text
  startSmoothReveal(msg)
}

function safeRevealLength(text: string, length: number) {
  // 避免把代理对（emoji 等）从中间截断，产生乱码
  const code = text.charCodeAt(length - 1)
  return code >= 0xd800 && code <= 0xdbff ? length - 1 : length
}

function startSmoothReveal(msg: any) {
  if (msg.revealTimer) return
  msg.rawContent = msg.rawContent || ''
  msg.revealStartedAt = Date.now()
  msg.revealedSeconds = '0.0'
  msg.lastRenderAt = 0
  msg.revealTimer = window.setInterval(() => {
    try {
      const raw: string = msg.rawContent || ''
      const shown: string = msg.content || ''
      if (raw.length <= shown.length) {
        if (msg.streamEnded) finishSmoothReveal(msg)
        return
      }
      const now = Date.now()
      const elapsed = (now - msg.revealStartedAt) / 1000
      // 按“已过时间 × 官网节奏”计算应显示到第几个字：内容一次性到齐也强制逐字铺开
      let rate = REVEAL_RATE
      if (raw.length / rate > REVEAL_MAX_SECONDS) rate = raw.length / REVEAL_MAX_SECONDS
      const target = Math.min(raw.length, Math.floor(elapsed * rate))
      if (target <= shown.length) return
      // 节流重绘：文本推进按 20ms 计算，但最多每 80ms 更新一次 DOM，避免卡顿
      const isFinal = target >= raw.length && msg.streamEnded
      if (!isFinal && now - (msg.lastRenderAt || 0) < REVEAL_RENDER_MS) return
      msg.lastRenderAt = now
      msg.revealedSeconds = elapsed.toFixed(1)
      msg.content = raw.slice(0, safeRevealLength(raw, target))
      scrollToBottom()
    } catch (err) {
      // 兜底：动画一旦出错就直接显示完整内容，绝不让回答卡住或消失
      console.error('[smooth-reveal] error', err)
      finishSmoothReveal(msg)
    }
  }, REVEAL_TICK_MS)
}

function finishSmoothReveal(msg: any) {
  if (msg.revealTimer) {
    window.clearInterval(msg.revealTimer)
    msg.revealTimer = null
  }
  if (msg.rawContent) msg.content = msg.rawContent
  msg.isStreaming = false
  msg.streamEnded = true
  scrollToBottom()
}

function flushSmoothReveal(msg: any) {
  msg.streamEnded = true
  finishSmoothReveal(msg)
}

function readyDocuments() {
  return documents.value.filter(doc => doc.status === 'ready')
}

function syncSelectedDocsForCurrentKb() {
  const readyDocs = readyDocuments()
  if (readyDocs.length === 1) {
    selectedDocIds.value = [readyDocs[0].id]
    return
  }

  const readyDocIds = new Set(readyDocs.map(doc => doc.id))
  selectedDocIds.value = selectedDocIds.value.filter(docId => readyDocIds.has(docId))
}

async function loadDocuments() {
  if (!selectedKb.value) {
    documents.value = []
    selectedDocIds.value = []
    return
  }
  try {
    const res = await kbApi.listDocs(selectedKb.value.id)
    documents.value = res.data
    syncSelectedDocsForCurrentKb()
  } catch {
    documents.value = []
    selectedDocIds.value = []
    ElMessage.error('加载文档列表失败')
  }
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function normalizeRenderedText(content: string) {
  return (content || '')
    .replace(/\r/g, '')
    .replace(/<sub>([\s\S]*?)<\/sub>/gi, '$1')
    .replace(/<sup>([\s\S]*?)<\/sup>/gi, '$1')
    .replace(/<br\s*\/?>(\n)?/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/`/g, '')
    .replace(/\n{3,}/g, '\n\n')
}

function normalizeMathDelimiters(content: string) {
  return (content || '')
    .replace(/\$\$([\s\S]+?)\$\$/g, '\\\[$1\\\]')
    .replace(/\$([^\n$]+?)\$/g, '\\($1\\)')
}

function renderMathExpression(expression: string, displayMode = false) {
  try {
    return katex.renderToString(expression, {
      throwOnError: false,
      displayMode,
      strict: 'ignore',
      trust: false,
    })
  } catch {
    return escapeHtml(expression)
  }
}

function renderAssistantHtml(content: string) {
  const normalized = normalizeMathDelimiters(normalizeRenderedText(content))
  const blockParts = normalized.split(/\n{2,}/)

  return blockParts.map(block => {
    const trimmedBlock = block.trim()
    if (!trimmedBlock) return ''

    if (/^\\\[[\s\S]*\\\]$/.test(trimmedBlock)) {
      return `<div class="math-block">${renderMathExpression(trimmedBlock.slice(2, -2), true)}</div>`
    }

    const html = escapeHtml(trimmedBlock)
      .replace(/\\\(([\s\S]+?)\\\)/g, (_, expr) => renderMathExpression(expr, false))
      .replace(/\\\[([\s\S]+?)\\\]/g, (_, expr) => `<div class="math-block">${renderMathExpression(expr, true)}</div>`)
      .replace(/\n/g, '<br>')

    return `<div class="assistant-paragraph">${html}</div>`
  }).join('')
}

function parsedSources(s: string): Source[] {
  try { return JSON.parse(s || '[]') } catch { return [] }
}

function noContextNotice(msg: any) {
  const content = (msg?.content || '').trim()
  const firstLine = content.split('\n')[0]?.trim() || ''
  if (msg?.noContextNotice) return msg.noContextNotice
  return firstLine === NO_CONTEXT_NOTICE ? firstLine : ''
}

function sanitizeAssistantContent(content: string, isStreaming = false) {
  const normalized = normalizeMathDelimiters((content || '')
    .replace(/\r/g, '')
    .replace(/\n{3,}/g, '\n\n'))
  return isStreaming ? normalized : normalized.trim()
}

function displayMessageContent(msg: any) {
  const content = sanitizeAssistantContent(msg?.content || '', !!msg?.isStreaming)
  const notice = noContextNotice(msg)
  if (!notice) return content
  return content.startsWith(notice) ? content.slice(notice.length).trimStart() : content
}

function showNoContextBanner(msg: any) {
  return msg?.role === 'assistant' && !msg?.isStreaming && !!(msg?.content || '').trim() && !parsedSources(msg.sources).length && !!noContextNotice(msg)
}

function isNoticeExpanded(messageIndex: number) {
  return !!expandedNoticeMap.value[messageIndex]
}

function toggleNoticeExpand(messageIndex: number) {
  expandedNoticeMap.value[messageIndex] = !expandedNoticeMap.value[messageIndex]
}

function appendActiveStreamingMessage(sessionId: number) {
  if (activeStreamingSessionId.value !== sessionId || !activeStreamingMessage.value) return
  if (messages.value.includes(activeStreamingMessage.value)) return
  messages.value.push(activeStreamingMessage.value)
}

function clearReadyStatusTimer() {
  if (readyStatusTimer !== null) {
    window.clearTimeout(readyStatusTimer)
    readyStatusTimer = null
  }
}

function markSessionReady(id: number | null) {
  if (!id) return
  processingSessionId.value = null
  readySessionId.value = id
  clearReadyStatusTimer()
  readyStatusTimer = window.setTimeout(() => {
    readySessionId.value = null
    readyStatusTimer = null
  }, 2500)
}

function sessionStatus(id: number) {
  if (processingSessionId.value === id) return 'processing'
  if (readySessionId.value === id) return 'ready'
  return ''
}

function isCurrentSessionStreaming() {
  return !!currentSessionId.value && currentSessionId.value === activeStreamingSessionId.value && isStreaming.value
}

async function loadAllKbs() {
  try { const res = await kbApi.list(); allKbs.value = res.data } catch { ElMessage.error('加载知识库失败') }
}

async function selectKb(kb: KnowledgeBase) {
  selectedKb.value = kb
  showKbSelect.value = false
  currentSessionId.value = null
  messages.value = []
  documents.value = []
  selectedDocIds.value = []
  expandedSourceMap.value = {}
  expandedNoticeMap.value = {}
  inputText.value = ''
  await Promise.all([loadSessions(), loadDocuments()])
}

function handleKbSelectorClick() {
  showKbSelect.value = true
}

async function refreshSessionsAndKeepSelection(preferredSessionId?: number | null) {
  await loadSessions()
  const targetId = preferredSessionId ?? currentSessionId.value
  if (!targetId) return
  const matched = sessions.value.find(s => s.id === targetId)
  if (matched) currentSessionId.value = matched.id
}

async function loadSessions() {
  if (!selectedKb.value) return
  try { const res = await chatApi.listSessions(selectedKb.value.id); sessions.value = res.data } catch { sessions.value = [] }
  await loadDocuments()
}

async function loadSession(id: number) {
  if (currentSessionId.value === id) return
  currentSessionId.value = id
  try {
    const res = await chatApi.getMessages(id)
    messages.value = res.data.map((m: any) => ({
      ...m,
      isStreaming: false,
      noContextNotice: '',
      toolSteps: parseToolSteps(m.tool_steps),
    }))
    appendActiveStreamingMessage(id)
    expandedSourceMap.value = {}
    expandedNoticeMap.value = {}
    await scrollToBottom()
  } catch { ElMessage.error('加载消息失败') }
}

function newSession() {
  currentSessionId.value = null
  messages.value = []
  expandedSourceMap.value = {}
  expandedNoticeMap.value = {}
  inputText.value = ''
  syncSelectedDocsForCurrentKb()
}

async function deleteSession(id: number) {
  if (processingSessionId.value === id) return
  try {
    await chatApi.deleteSession(id)
    if (currentSessionId.value === id) {
      currentSessionId.value = null
      messages.value = []
      expandedSourceMap.value = {}
    }
    await refreshSessionsAndKeepSelection()
  } catch { ElMessage.error('删除失败') }
}

function quickQuestion(q: string) { inputText.value = q; sendMessage() }

function stopStreaming() {
  if (!isStreaming.value || !currentAbortController) return
  isStopping.value = true
  currentAbortController.abort()
}

async function sendMessage() {
  if (!selectedKb.value || !inputText.value.trim() || isStreaming.value) return
  const question = inputText.value.trim()
  const originSessionId = currentSessionId.value
  inputText.value = ''
  isStreaming.value = true
  isStopping.value = false
  processingSessionId.value = originSessionId
  readySessionId.value = null
  clearReadyStatusTimer()
  messages.value.push({ role: 'user', content: question, sources: '[]', isStreaming: false })
  const assistantMsgDraft: any = { role: 'assistant', content: '', rawContent: '', sources: '[]', toolSteps: [] as AgentToolStep[], isStreaming: true, streamEnded: false, revealTimer: null, noContextNotice: '', statusText: '', elapsed: '' }
  messages.value.push(assistantMsgDraft)
  // 关键：必须取数组中的「响应式代理」来后续更新。
  // 直接修改上面那个原始对象不会触发视图刷新（Vue 3 响应式陷阱），会导致
  // “数据已到但界面不更新、文字一次性蹦出 / 卡住不动”的现象。
  const assistantMsg: any = messages.value[messages.value.length - 1]
  activeStreamingSessionId.value = originSessionId
  activeStreamingMessage.value = assistantMsg
  // 实时计时器：让用户看到系统确实在持续工作（检索 + 生成耗时）
  const streamStartedAt = Date.now()
  const statusTimer = window.setInterval(() => {
    assistantMsg.elapsed = ((Date.now() - streamStartedAt) / 1000).toFixed(1)
  }, 100)
  // 卡死看门狗：超过 25 秒没有收到任何新数据就主动收尾，避免界面无限等待
  let lastDataAt = Date.now()
  let stalled = false
  const stallTimer = window.setInterval(() => {
    if (!isStreaming.value || stalled) return
    if (Date.now() - lastDataAt > 25000) {
      stalled = true
      try { currentAbortController?.abort() } catch {}
    }
  }, 1000)
  await scrollToBottom()
  let streamSessionId: number | null = originSessionId
  let requestFailed = false
  try {
    currentAbortController = new AbortController()
    const payload: ChatRequestPayload = {
      question,
      session_id: originSessionId ?? undefined,
      kb_id: selectedKb.value.id,
      selected_doc_ids: selectedDocIds.value,
      agent_mode: agentMode.value,
    }
    const url = chatApi.streamChat(payload)
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: currentAbortController.signal,
    })
    if (!resp.ok || !resp.body) throw new Error('Stream request failed')
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      lastDataAt = Date.now()
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n'); buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        if (data === '[DONE]') {
          // 网络流结束，但界面继续把剩余文字平滑输出完
          assistantMsg.streamEnded = true
          activeStreamingSessionId.value = null
          activeStreamingMessage.value = null
          await loadSessions()
          markSessionReady(streamSessionId)
          break
        }
        if (data.startsWith('[META]')) {
          try {
            const meta = JSON.parse(data.slice(6))
            if (meta.session_id) {
              streamSessionId = meta.session_id
              processingSessionId.value = meta.session_id
              activeStreamingSessionId.value = meta.session_id
              await loadSessions()
              if (currentSessionId.value === originSessionId) currentSessionId.value = meta.session_id
            }
            if (meta.sources) assistantMsg.sources = JSON.stringify(meta.sources)
            if (meta.no_context) assistantMsg.noContextNotice = meta.notice || NO_CONTEXT_NOTICE
          } catch {}
          continue
        }
        try {
          const parsed = JSON.parse(data)
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && parsed.type) {
            handleAgentEvent(parsed, assistantMsg)
          } else {
            appendStreamText(assistantMsg, parsed)
          }
        } catch {}
      }
    }
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      flushSmoothReveal(assistantMsg)
      if (stalled) {
        assistantMsg.content = (assistantMsg.content ? assistantMsg.content + '\n\n' : '') + '[连接已中断：超过 25 秒没有收到新数据，已保留已生成的内容。请重新提问。]'
      } else {
        assistantMsg.content = assistantMsg.content || '已停止回答'
      }
      activeStreamingSessionId.value = null
      activeStreamingMessage.value = null
      processingSessionId.value = null
      await loadSessions()
      if (streamSessionId) markSessionReady(streamSessionId)
    } else {
      requestFailed = true
      processingSessionId.value = null
      flushSmoothReveal(assistantMsg)
      assistantMsg.content = (assistantMsg.content ? assistantMsg.content + '\n\n' : '') + '请求失败：' + (e?.message || '未知错误')
      activeStreamingSessionId.value = null
      activeStreamingMessage.value = null
      ElMessage.error('问答请求失败')
    }
  } finally {
    window.clearInterval(statusTimer)
    window.clearInterval(stallTimer)
    currentAbortController = null
    isStopping.value = false
    isStreaming.value = false
    assistantMsg.statusText = ''
    // 让剩余文字继续“流”完；若未启动平滑输出则直接收尾
    if (assistantMsg.revealTimer) {
      assistantMsg.streamEnded = true
    } else if (assistantMsg.isStreaming) {
      finishSmoothReveal(assistantMsg)
    }
    if (!requestFailed && processingSessionId.value === streamSessionId) markSessionReady(streamSessionId)
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (msgArea.value) msgArea.value.scrollTop = msgArea.value.scrollHeight
}

onMounted(async () => {
  await loadAllKbs()
  const kbIdFromRoute = route.query.kb_id
  if (kbIdFromRoute) { const kb = allKbs.value.find(k => k.id === Number(kbIdFromRoute)); if (kb) await selectKb(kb) }
})
</script>

<style scoped>
.chat-layout { display:flex; height:100%; overflow:hidden; background:var(--bg); }
.sessions-panel { width:240px; min-width:240px; border-right:1px solid var(--border); display:flex; flex-direction:column; background:var(--bg-sidebar); overflow:hidden; }
.sessions-header { display:flex; align-items:center; justify-content:space-between; padding:16px 16px 8px; font-size:13px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px; }
.kb-selector { display:flex; align-items:center; gap:8px; margin:0 12px 8px; padding:10px 12px; background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-sm); cursor:pointer; transition:var(--transition); font-size:13px; color:var(--text); }
.kb-selector:hover { border-color:var(--primary); }
.kb-selector.empty { color:var(--text-muted); border-style:dashed; }
.kb-sel-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.new-chat-btn { margin:0 12px 8px; width:calc(100% - 24px); border:1px dashed var(--border); color:var(--text-muted); }
.new-chat-btn:hover { border-color:var(--primary); color:var(--primary-light); }
.session-list { flex:1; overflow-y:auto; padding:4px 8px; }
.session-item { display:flex; align-items:center; gap:8px; padding:9px 10px; border-radius:var(--radius-sm); cursor:pointer; transition:var(--transition); font-size:13px; color:var(--text-muted); }
.session-item:hover { background:var(--bg-hover); color:var(--text); }
.session-item.active { background:rgba(37,99,235,0.15); color:#60a5fa; }
.session-title { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.session-status-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; box-shadow:0 0 0 2px rgba(255,255,255,0.03); }
.session-status-dot.processing { background:#94a3b8; }
.session-status-dot.ready { background:#22c55e; box-shadow:0 0 10px rgba(34,197,94,0.45); }
.del-btn { opacity:0; transition:var(--transition); color:var(--text-muted) !important; }
.session-item:hover .del-btn { opacity:1; }
.del-btn.is-disabled { opacity:0.25 !important; cursor:not-allowed; }
.empty-sessions { text-align:center; color:var(--text-muted); font-size:13px; padding:24px 0; }
.chat-main { flex:1; display:flex; flex-direction:column; overflow:hidden; min-height:0; }
 .chat-header { padding:16px 24px; border-bottom:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
.chat-header h2 { font-size:16px; font-weight:600; color:var(--text); }
.doc-picker-wrap { display:flex; align-items:center; gap:10px; margin-left:auto; max-width:min(100%, 520px); }
.doc-picker-label { font-size:12px; color:var(--text-muted); white-space:nowrap; }
.doc-picker { min-width:260px; max-width:520px; }
.chat-welcome { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:16px; padding:40px; animation:fadeIn 0.4s ease; }
.welcome-icon { width:80px; height:80px; background:linear-gradient(135deg,rgba(6,182,212,0.1),rgba(37,99,235,0.15)); border-radius:20px; display:flex; align-items:center; justify-content:center; border:1px solid rgba(6,182,212,0.2); }
.chat-welcome h3 { font-size:22px; font-weight:700; color:var(--text); }
 .chat-welcome p { color:var(--text-muted); font-size:14px; }
.welcome-doc-hint { margin-top:4px; padding:10px 14px; border-radius:10px; border:1px solid rgba(96,165,250,.18); background:rgba(37,99,235,.08); color:#bfd8ff; font-size:12px; }
.welcome-tips { display:flex; flex-direction:column; gap:8px; margin-top:8px; width:100%; max-width:500px; }
.tip { padding:12px 16px; background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-sm); cursor:pointer; font-size:14px; color:var(--text-muted); transition:var(--transition); }
.tip:hover { border-color:var(--primary); color:var(--text); background:var(--bg-hover); }
.messages-area { flex:1; min-height:0; overflow-y:auto; overscroll-behavior:contain; padding:24px; display:flex; flex-direction:column; gap:20px; }
.message-row { display:flex; gap:12px; align-items:flex-start; animation:fadeIn 0.2s ease; }
.message-row.user { flex-direction:row-reverse; }
.avatar { width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.message-row.user .avatar { background:linear-gradient(135deg,var(--primary),var(--primary-light)); color:white; }
.message-row.assistant .avatar { background:linear-gradient(135deg,#0c2040,#1a3a6b); color:var(--accent); border:1px solid rgba(6,182,212,0.3); }
.bubble-wrap { display:flex; flex-direction:column; gap:8px; max-width:75%; }
.message-row.user .bubble-wrap { align-items:flex-end; }
.bubble { padding:12px 16px; border-radius:12px; font-size:14px; line-height:1.6; }
.bubble.user { background:linear-gradient(135deg,var(--primary),var(--primary-dark)); color:white; border-bottom-right-radius:4px; }
.bubble.assistant { background:var(--bg-card); border:1px solid var(--border); color:var(--text); border-bottom-left-radius:4px; }
.assistant-rich { white-space:normal; line-height:1.75; }
/* 流式输出期间用纯文本渲染：只更新文本节点，避免高频 v-html 重排导致卡顿 */
.streaming-plain { white-space:pre-wrap; word-break:break-word; }
.assistant-paragraph + .assistant-paragraph { margin-top:10px; }
.assistant-rich :deep(.katex-display) { margin:10px 0; overflow-x:auto; overflow-y:hidden; }
.assistant-rich :deep(.katex) { font-size:1.05em; }
.math-block { margin:10px 0; overflow-x:auto; overflow-y:hidden; }
.thinking { display:flex; gap:4px; padding:4px 0; align-items:center; }
.dot-pulse { width:6px; height:6px; border-radius:50%; background:var(--accent); animation:pulse 1.2s infinite; }
.dot-pulse:nth-child(2) { animation-delay:0.2s; }
.dot-pulse:nth-child(3) { animation-delay:0.4s; }
.cursor-blink { animation:pulse 0.8s infinite; }
.sources { margin-top:4px; }
.sources-toggle { display:flex; justify-content:center; margin-top:6px; }
.sources-title { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--text-muted); }
.source-item { padding:8px 12px; background:var(--bg); border-radius:6px; margin-top:6px; border:1px solid var(--border); }
.source-group { padding:10px 12px; background:var(--bg); border-radius:8px; margin-top:6px; border:1px solid var(--border); }
.source-doc { display:flex; align-items:center; gap:6px; min-width:0; }
.source-doc span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.source-meta { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.source-header { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:12px; color:var(--text-muted); margin-bottom:4px; flex-wrap:wrap; }
.source-content { font-size:12px; color:var(--text-muted); line-height:1.5; white-space:pre-wrap; }
.no-context-inline { display:flex; align-items:flex-start; gap:8px; margin-top:4px; }
.no-context-toggle { width:28px; height:28px; border:none; border-radius:999px; background:rgba(245,158,11,.14); color:#f59e0b; display:flex; align-items:center; justify-content:center; cursor:pointer; transition:var(--transition); box-shadow:inset 0 0 0 1px rgba(245,158,11,.22); }
.no-context-toggle:hover { background:rgba(245,158,11,.2); transform:translateY(-1px); }
.no-context-banner { padding:10px 12px; border:1px solid rgba(245,158,11,.24); border-radius:8px; background:rgba(245,158,11,.08); color:#f7d58d; font-size:12px; line-height:1.6; cursor:pointer; }
.notice-fade-enter-active, .notice-fade-leave-active { transition:opacity .18s ease, transform .18s ease; }
.notice-fade-enter-from, .notice-fade-leave-to { opacity:0; transform:translateX(-6px); }
.input-area { padding:16px 24px; border-top:1px solid var(--border); display:flex; flex-direction:column; gap:8px; }
.input-actions { display:flex; align-items:center; justify-content:flex-end; gap:12px; }
.speed-wrap { display:flex; align-items:center; gap:8px; margin-right:auto; }
.build-tag { font-size:11px; color:var(--text-muted); opacity:.7; padding:2px 7px; border:1px solid var(--border); border-radius:999px; white-space:nowrap; }
.diag-btn { font-size:11.5px; color:var(--text-muted) !important; text-decoration:underline; }
.diag-body { display:flex; flex-direction:column; gap:12px; }
.diag-log { margin:0; padding:12px; max-height:360px; overflow:auto; border-radius:8px; background:rgba(7,14,29,.55); border:1px solid var(--border); color:var(--text); font-size:12px; line-height:1.7; white-space:pre-wrap; word-break:break-all; font-family:Consolas, Monaco, monospace; }
.reveal-line { display:flex; align-items:center; gap:6px; margin-top:8px; font-size:11.5px; color:var(--accent); opacity:.85; }
.hint { font-size:12px; color:var(--text-muted); }
.agent-mode-wrap { display:flex; align-items:center; gap:8px; margin-left:16px; padding:6px 12px; border:1px solid rgba(6,182,212,.25); border-radius:999px; background:rgba(6,182,212,.08); }
.agent-mode-label { font-size:12px; color:var(--accent); white-space:nowrap; }
.stream-status { display:flex; align-items:center; gap:8px; margin-bottom:10px; padding:7px 12px; border-radius:8px; background:rgba(6,182,212,.07); border:1px solid rgba(6,182,212,.2); font-size:12.5px; color:var(--text-muted); }
.status-loader { width:12px; height:12px; border-radius:50%; border:2px solid rgba(6,182,212,.25); border-top-color:var(--accent); animation:status-spin .7s linear infinite; flex-shrink:0; }
.status-text { color:var(--text); }
.status-elapsed { margin-left:auto; font-family:Consolas, Monaco, monospace; font-size:11.5px; color:var(--accent); opacity:.85; }
@keyframes status-spin { to { transform:rotate(360deg); } }
.tool-steps { display:flex; flex-direction:column; gap:6px; margin-bottom:10px; }
.tool-step { border:1px solid rgba(6,182,212,.22); background:rgba(6,182,212,.06); border-radius:8px; padding:8px 10px; font-size:12px; }
.tool-step.running { border-color:rgba(245,158,11,.35); background:rgba(245,158,11,.07); }
.tool-step-head { display:flex; align-items:center; gap:6px; }
.tool-icon { color:var(--accent); flex-shrink:0; }
.tool-name { font-weight:600; color:var(--text); }
.tool-status { margin-left:auto; font-size:11px; }
.tool-status.running { color:#f59e0b; }
.tool-args { margin-top:4px; color:var(--text-muted); font-family:Consolas, Monaco, monospace; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tool-result { margin-top:4px; color:#7dd3fc; font-family:Consolas, Monaco, monospace; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.kb-list { display:flex; flex-direction:column; gap:8px; max-height:400px; overflow-y:auto; padding:4px; }
.kb-option { display:flex; align-items:center; gap:12px; padding:14px 16px; border:1px solid var(--border); border-radius:var(--radius-sm); cursor:pointer; transition:var(--transition); color:var(--text-muted); }
.kb-option:hover { border-color:var(--primary); background:var(--bg-hover); color:var(--text); }
.kb-option.active { border-color:var(--primary); background:rgba(37,99,235,0.1); color:#60a5fa; }
.kb-opt-name { font-size:14px; font-weight:500; color:var(--text); }
.kb-opt-desc { font-size:12px; color:var(--text-muted); margin-top:2px; }
</style>
