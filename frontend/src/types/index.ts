export interface KnowledgeBase {
  id: number
  name: string
  description: string
  document_count: number
  created_at: string
  updated_at: string
}

export interface Document {
  id: number
  kb_id: number
  filename: string
  original_name: string
  file_size: number
  file_type: string
  status: 'processing' | 'ready' | 'failed'
  chunk_count: number
  progress_percent: number
  progress_message: string
  created_at: string
  error_message: string
}

export interface ChatSession {
  id: number
  kb_id: number
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  sources: string
  created_at: string
}

export interface Source {
  content: string
  filename: string
  score: number
}
