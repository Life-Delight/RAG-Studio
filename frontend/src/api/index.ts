import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || ''

export const http = axios.create({
  baseURL: BASE_URL,
  timeout: 300000,
})

http.interceptors.response.use(
  res => res,
  err => {
    console.error('API Error:', err)
    return Promise.reject(err)
  }
)

// Knowledge Base APIs
export const kbApi = {
  list: () => http.get('/api/knowledge-bases'),
  create: (data: { name: string; description?: string }) =>
    http.post('/api/knowledge-bases', data),
  get: (id: number) => http.get(`/api/knowledge-bases/${id}`),
  update: (id: number, data: { name?: string; description?: string }) =>
    http.put(`/api/knowledge-bases/${id}`, data),
  delete: (id: number) => http.delete(`/api/knowledge-bases/${id}`),
  listDocs: (id: number) => http.get(`/api/knowledge-bases/${id}/documents`),
  uploadDoc: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post(`/api/knowledge-bases/${id}/documents`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  uploadDocsBatch: (id: number, files: File[]) => {
    const form = new FormData()
    files.forEach(file => form.append('files', file))
    return http.post(`/api/knowledge-bases/${id}/documents/batch`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  deleteDoc: (kbId: number, docId: number) =>
    http.delete(`/api/knowledge-bases/${kbId}/documents/${docId}`),
}

// Chat APIs
export const chatApi = {
  listSessions: (kbId?: number) =>
    http.get('/api/chat/sessions', { params: kbId ? { kb_id: kbId } : {} }),
  createSession: (data: { kb_id: number; title?: string }) =>
    http.post('/api/chat/sessions', data),
  deleteSession: (id: number) => http.delete(`/api/chat/sessions/${id}`),
  getMessages: (sessionId: number) =>
    http.get(`/api/chat/sessions/${sessionId}/messages`),
  streamChat: (data: { question: string; session_id?: number; kb_id: number; selected_doc_ids?: number[]; agent_mode?: boolean }) =>
    `${BASE_URL}/api/chat/stream`,
  // 流式自检：服务端每 100ms 推一块，用于判断浏览器/代理是否缓冲 SSE
  diagStream: () => `${BASE_URL}/api/chat/diag-stream`,
}
