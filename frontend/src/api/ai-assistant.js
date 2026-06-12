import api from '@/utils/api'

export function sendMessage(data) {
  return api.post('/ai-assistant/chat/send_message/', data).then(r => r.data)
}

export function getSessions() {
  return api.get('/ai-assistant/sessions/').then(r => r.data.results || r.data)
}

export function getSessionMessages(sessionId) {
  return api.get(`/ai-assistant/sessions/${sessionId}/messages/`).then(r => r.data)
}

export function deleteSession(sessionId) {
  return api.delete(`/ai-assistant/sessions/${sessionId}/`)
}
