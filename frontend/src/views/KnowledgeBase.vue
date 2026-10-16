<template>
  <div class="kb-page">
    <div class="page-header fade-in">
      <div>
        <h1 class="page-title">知识库管理</h1>
        <p class="page-sub">构建私有知识空间，支持 PDF / Word / TXT / Markdown / CSV</p>
      </div>
      <el-button type="primary" size="large" @click="showCreate = true">
        <el-icon><Plus /></el-icon> 新建知识库
      </el-button>
    </div>

    <div class="overview-row fade-in">
      <div class="overview-card">
        <span class="num">{{ knowledgeBases.length }}</span>
        <span class="label">知识库数量</span>
      </div>
      <div class="overview-card">
        <span class="num">{{ totalDocs }}</span>
        <span class="label">文档总数</span>
      </div>
      <div class="overview-card">
        <span class="num">{{ latestUpdate }}</span>
        <span class="label">最近更新</span>
      </div>
    </div>

    <div class="kb-grid" v-loading="loading">
      <div
        v-for="kb in knowledgeBases"
        :key="kb.id"
        class="kb-card"
        @click="goDetail(kb.id)"
      >
        <div class="kb-card-header">
          <div class="kb-icon">
            <el-icon size="22"><Collection /></el-icon>
          </div>
          <div class="kb-actions" @click.stop>
            <el-button text size="small" @click="openEdit(kb)">
              <el-icon><Edit /></el-icon>
            </el-button>
            <el-button text size="small" type="danger" @click="confirmDelete(kb)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
        <div class="kb-card-body">
          <h3 class="kb-name">{{ kb.name }}</h3>
          <p class="kb-desc">{{ kb.description || '暂无描述' }}</p>
        </div>
        <div class="kb-card-footer">
          <span class="kb-stat">
            <el-icon><Document /></el-icon>
            {{ kb.document_count }} 个文档
          </span>
          <span class="kb-date">{{ formatDate(kb.updated_at) }}</span>
        </div>
      </div>

      <div class="kb-card kb-card-add" @click="showCreate = true">
        <el-icon size="32"><Plus /></el-icon>
        <span>新建知识库</span>
      </div>
    </div>

    <el-empty v-if="!loading && knowledgeBases.length === 0" description="暂无知识库，点击新建" />

    <el-dialog v-model="showCreate" title="新建知识库" width="480px" :close-on-click-modal="false">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="请输入知识库名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="可选描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEdit" title="编辑知识库" width="480px" :close-on-click-modal="false">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="editForm.name" placeholder="请输入知识库名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="可选描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Collection, Delete, Document, Edit, Plus } from '@element-plus/icons-vue'
import { kbApi } from '@/api'
import type { KnowledgeBase } from '@/types'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const knowledgeBases = ref<KnowledgeBase[]>([])
const showCreate = ref(false)
const showEdit = ref(false)
const editTarget = ref<KnowledgeBase | null>(null)
const createForm = ref({ name: '', description: '' })
const editForm = ref({ name: '', description: '' })

const totalDocs = computed(() => knowledgeBases.value.reduce((s, i) => s + (i.document_count || 0), 0))
const latestUpdate = computed(() => {
  if (!knowledgeBases.value.length) return '-'
  const latest = knowledgeBases.value
    .map(i => new Date(i.updated_at).getTime())
    .sort((a, b) => b - a)[0]
  return new Date(latest).toLocaleDateString('zh-CN')
})

async function fetchKBs() {
  loading.value = true
  try {
    const res = await kbApi.list()
    knowledgeBases.value = res.data
  } catch {
    ElMessage.error('加载知识库失败')
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!createForm.value.name.trim()) return ElMessage.warning('请输入名称')
  submitting.value = true
  try {
    await kbApi.create(createForm.value)
    ElMessage.success('创建成功')
    showCreate.value = false
    createForm.value = { name: '', description: '' }
    await fetchKBs()
  } catch {
    ElMessage.error('创建失败')
  } finally {
    submitting.value = false
  }
}

function openEdit(kb: KnowledgeBase) {
  editTarget.value = kb
  editForm.value = { name: kb.name, description: kb.description }
  showEdit.value = true
}

async function handleEdit() {
  if (!editForm.value.name.trim()) return ElMessage.warning('请输入名称')
  submitting.value = true
  try {
    await kbApi.update(editTarget.value!.id, editForm.value)
    ElMessage.success('更新成功')
    showEdit.value = false
    await fetchKBs()
  } catch {
    ElMessage.error('更新失败')
  } finally {
    submitting.value = false
  }
}

async function confirmDelete(kb: KnowledgeBase) {
  await ElMessageBox.confirm(`确认删除知识库「${kb.name}」？此操作不可恢复。`, '删除确认', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  })
  try {
    await kbApi.delete(kb.id)
    ElMessage.success('删除成功')
    await fetchKBs()
  } catch {
    ElMessage.error('删除失败')
  }
}

function goDetail(id: number) {
  router.push(`/knowledge-base/${id}`)
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('zh-CN')
}

onMounted(fetchKBs)
</script>

<style scoped>
.kb-page {
  padding: 32px;
  height: 100%;
  overflow-y: auto;
  background: transparent;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}

.page-title {
  font-size: 30px;
  font-weight: 800;
  letter-spacing: .2px;
  margin-bottom: 6px;
}

.page-sub {
  font-size: 14px;
  color: var(--text-muted);
}

.overview-row {
  display: flex;
  gap: 12px;
  margin-bottom: 22px;
}

.overview-card {
  min-width: 140px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 10px 16px;
  backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.overview-card .num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #bcd1ff;
}

.overview-card .label {
  font-size: 12px;
  color: var(--text-muted);
}

.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.kb-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  cursor: pointer;
  transition: var(--transition);
  display: flex;
  flex-direction: column;
  gap: 12px;
  backdrop-filter: blur(12px);
}

.kb-card:hover {
  border-color: rgba(122,162,255,.56);
  box-shadow: 0 0 0 1px rgba(122,162,255,.3), var(--shadow-soft);
  transform: translateY(-3px);
}

.kb-card-add {
  align-items: center;
  justify-content: center;
  border-style: dashed;
  color: var(--text-muted);
  font-size: 14px;
  gap: 8px;
  min-height: 170px;
}

.kb-card-add:hover {
  color: #bbd2ff;
}

.kb-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.kb-icon {
  width: 46px;
  height: 46px;
  background: linear-gradient(135deg, rgba(79,124,255,0.22), rgba(45,212,191,0.14));
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8ab3ff;
  border: 1px solid rgba(122,162,255,.4);
}

.kb-name {
  font-size: 17px;
  font-weight: 700;
}

.kb-desc {
  font-size: 13px;
  color: var(--text-muted);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.kb-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.kb-stat {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

.kb-date {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
