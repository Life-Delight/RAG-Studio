import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/knowledge-base'
    },
    {
      path: '/knowledge-base',
      name: 'KnowledgeBase',
      component: () => import('@/views/KnowledgeBase.vue'),
      meta: { title: '知识库管理' }
    },
    {
      path: '/knowledge-base/:id',
      name: 'KnowledgeBaseDetail',
      component: () => import('@/views/KnowledgeBaseDetail.vue'),
      meta: { title: '知识库详情' }
    },
    {
      path: '/chat',
      name: 'Chat',
      component: () => import('@/views/Chat.vue'),
      meta: { title: '智能问答' }
    }
  ]
})

export default router
