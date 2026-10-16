<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-glow"></div>

      <div class="sidebar-logo">
        <div class="logo-icon float">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#8de9ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <div>
          <div class="logo-text">RAG Studio</div>
          <div class="logo-sub">Private Knowledge Assistant</div>
        </div>
      </div>

      <nav class="sidebar-nav">
        <router-link to="/knowledge-base" class="nav-item" active-class="active">
          <el-icon><FolderOpened /></el-icon>
          <span>知识库管理</span>
        </router-link>
        <router-link to="/chat" class="nav-item" active-class="active">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能问答</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="model-badge">
          <span class="dot"></span>
          <span>deepseek-chat</span>
        </div>
        <div class="model-sub">DeepSeek API · 云端推理</div>
      </div>
    </aside>

    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ChatDotRound, FolderOpened } from '@element-plus/icons-vue'
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: transparent;
}

.sidebar {
  width: 244px;
  min-width: 244px;
  position: relative;
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(14px);
}

.sidebar-glow {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 0% 0%, rgba(79,124,255,.18), transparent 40%),
    radial-gradient(circle at 110% 110%, rgba(45,212,191,.12), transparent 36%);
  pointer-events: none;
}

.sidebar-logo {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 22px 20px;
  border-bottom: 1px solid var(--border);
}

.logo-icon {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #20345f 0%, #214b7a 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(129, 173, 255, 0.45);
  box-shadow: inset 0 0 22px rgba(141,233,255,.12);
}

.logo-text {
  font-size: 18px;
  line-height: 1.1;
  font-weight: 800;
  letter-spacing: .3px;
}

.logo-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

.sidebar-nav {
  position: relative;
  z-index: 1;
  flex: 1;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: var(--transition);
  border: 1px solid transparent;
}

.nav-item:hover {
  background: var(--bg-hover);
  border-color: rgba(126, 154, 222, .24);
  color: var(--text);
  transform: translateX(2px);
}

.nav-item.active {
  background: linear-gradient(135deg, rgba(79,124,255,0.26), rgba(45,212,191,0.15));
  color: #b8d6ff;
  border: 1px solid rgba(133, 170, 255, 0.42);
  box-shadow: inset 0 0 16px rgba(79,124,255,.2);
}

.sidebar-footer {
  position: relative;
  z-index: 1;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}

.model-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text);
  font-family: 'JetBrains Mono', monospace;
  font-weight: 500;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 10px var(--success);
  animation: pulse 2s infinite;
}

.model-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  padding-left: 16px;
}

.main-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.page-enter-active,
.page-leave-active {
  transition: opacity .24s ease, transform .24s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateX(10px) scale(.995);
}

.page-leave-to {
  opacity: 0;
  transform: translateX(-10px) scale(.995);
}
</style>
