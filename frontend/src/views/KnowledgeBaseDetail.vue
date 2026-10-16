<template>
  <div class="detail-page">
    <div class="page-header fade-in">
      <div class="header-left">
        <el-button text @click="router.push('/knowledge-base')">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <div>
          <h1 class="page-title">{{ kb?.name }}</h1>
          <p class="page-sub">{{ kb?.description || '暂无描述' }}</p>
        </div>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="goChat">
          <el-icon><ChatDotRound /></el-icon> 开始问答
        </el-button>
        <el-button :loading="uploading" @click="openFilePicker">
          <el-icon><Upload /></el-icon> 批量上传文档
        </el-button>
        <input
          ref="fileInputRef"
          type="file"
          accept=".txt,.pdf,.docx,.doc,.md,.csv"
          multiple
          style="display: none"
          @change="handleFileInputChange"
        />
      </div>
    </div>

    <div class="stats-row fade-in">
      <div class="stat-card">
        <span class="stat-num">{{ documents.length }}</span>
        <span class="stat-label">文档总数</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ readyCount }}</span>
        <span class="stat-label">已就绪</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ totalChunks }}</span>
        <span class="stat-label">知识块总数</span>
      </div>
    </div>

    <div class="table-shell fade-in">
      <el-table
        v-loading="loading"
        :data="documents"
        style="width: 100%"
        empty-text="暂无文档，请上传"
      >
        <el-table-column label="文件名" prop="original_name" min-width="220">
          <template #default="{ row }">
            <div class="file-name">
              <el-icon class="file-icon"><DocumentIcon /></el-icon>
              {{ row.original_name }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" prop="file_type" width="90" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="240">
          <template #default="{ row }">
            <div class="status-cell">
              <el-tag :type="statusType(row.status)" size="small">
                <span v-if="row.status === 'processing'" class="processing-dot"></span>
                {{ statusLabel(row.status) }}
              </el-tag>
              <template v-if="row.status === 'processing'">
                <el-progress
                  :percentage="row.progress_percent || 0"
                  :stroke-width="6"
                  :show-text="true"
                  :text-inside="false"
                  class="doc-progress"
                />
                <div class="progress-msg">{{ row.progress_message || '处理中...' }}</div>
              </template>
              <div v-else-if="row.status === 'failed'" class="progress-msg failed-msg">
                {{ row.error_message || '处理失败' }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="知识块数" prop="chunk_count" width="90" />
        <el-table-column label="上传时间" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button text type="danger" size="small" @click.stop="confirmDeleteDoc(row)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ChatDotRound, Delete, Document as DocumentIcon, Upload } from '@element-plus/icons-vue'
import { kbApi } from '@/api'
import type { KnowledgeBase, Document } from '@/types'

const router = useRouter()
const route = useRoute()
const kbId = Number(route.params.id)

const loading = ref(false)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const kb = ref<KnowledgeBase | null>(null)
const documents = ref<Document[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const readyCount = computed(() => documents.value.filter(d => d.status === 'ready').length)
const totalChunks = computed(() => documents.value.reduce((s, d) => s + d.chunk_count, 0))

async function fetchKB() {
  try {
    const res = await kbApi.get(kbId)
    kb.value = res.data
  } catch {
    ElMessage.error('知识库不存在')
    router.push('/knowledge-base')
  }
}

async function fetchDocs() {
  loading.value = true
  try {
    const res = await kbApi.listDocs(kbId)
    documents.value = res.data
  } finally {
    loading.value = false
  }
}

function openFilePicker() {
  if (uploading.value) return
  fileInputRef.value?.click()
}

async function handleFileInputChange(event: Event) {
  const input = event.target as HTMLInputElement
  const selectedFiles = Array.from(input.files || [])
  if (!selectedFiles.length) return

  uploading.value = true
  try {
    const res = await kbApi.uploadDocsBatch(kbId, selectedFiles)
    const data = res.data || {}
    const success = data.success ?? 0
    const failed = data.failed ?? 0

    if (success > 0 && failed === 0) {
      ElMessage.success(`上传成功，共 ${success} 个文件，正在处理...`)
    } else if (success > 0) {
      ElMessage.warning(`上传完成：成功 ${success} 个，失败 ${failed} 个`)
    } else {
      ElMessage.error('上传失败，请检查文件格式')
    }

    if (Array.isArray(data.results)) {
      const firstFailed = data.results.find((item: any) => !item.ok)
      if (firstFailed?.error) {
        ElMessage.error(`失败示例：${firstFailed.filename} - ${firstFailed.error}`)
      }
    }

    await fetchDocs()
    startPolling()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  } finally {
    if (fileInputRef.value) fileInputRef.value.value = ''
    uploading.value = false
  }
}

async function confirmDeleteDoc(doc: Document) {
  await ElMessageBox.confirm(`确认删除文档「${doc.original_name}」？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  try {
    await kbApi.deleteDoc(kbId, doc.id)
    ElMessage.success('删除成功')
    await fetchDocs()
  } catch {
    ElMessage.error('删除失败')
  }
}

function goChat() {
  router.push({ path: '/chat', query: { kb_id: kbId } })
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    const hasProcessing = documents.value.some(d => d.status === 'processing')
    if (hasProcessing) {
      await fetchDocs()
      await fetchKB()
    } else {
      stopPolling()
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function statusType(s: string) {
  return s === 'ready' ? 'success' : s === 'failed' ? 'danger' : 'warning'
}

function statusLabel(s: string) {
  return s === 'ready' ? '就绪' : s === 'failed' ? '失败' : '处理中'
}

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

function formatDate(d: string) {
  return new Date(d).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

onMounted(async () => {
  await fetchKB()
  await fetchDocs()
  if (documents.value.some(d => d.status === 'processing')) startPolling()
})

onBeforeUnmount(stopPolling)
</script>

<style scoped>
.detail-page {
  padding: 32px;
  height: 100%;
  overflow-y: auto;
  background: transparent;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.page-title {
  font-size: 28px;
  line-height: 1.15;
  font-weight: 800;
}

.page-sub {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 6px;
}

.stats-row {
  display: flex;
  gap: 16px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 140px;
  backdrop-filter: blur(12px);
}

.stat-num {
  font-size: 30px;
  font-weight: 700;
  color: #9dbbff;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.table-shell {
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  overflow: hidden;
}

.file-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-icon {
  color: var(--accent-soft);
}

.processing-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--warning);
  animation: pulse 1.2s infinite;
  margin-right: 4px;
}

.status-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.doc-progress {
  width: 170px;
}

.progress-msg {
  font-size: 12px;
  color: var(--text-muted);
  max-width: 190px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.failed-msg {
  color: #ff9a9a;
}
</style>
