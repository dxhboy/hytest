import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sendMessage, getSessions, getSessionMessages, deleteSession } from '@/api/ai-assistant'

export const useAiAssistantStore = defineStore('aiAssistant', () => {
  const isOpen = ref(false)
  const currentSessionId = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const toolsInProgress = ref([])
  const error = ref(null)

  function togglePanel() {
    isOpen.value = !isOpen.value
  }

  function closePanel() {
    isOpen.value = false
  }

  function startNewSession() {
    currentSessionId.value = null
    messages.value = []
    error.value = null
  }

  async function send(message, context) {
    if (!message.trim()) return
    loading.value = true
    error.value = null
    toolsInProgress.value = []  // 重置上次的工具调用记录

    const userMsg = { role: 'user', content: message, created_at: new Date().toISOString() }
    messages.value.push(userMsg)

    try {
      const res = await sendMessage({
        session_id: currentSessionId.value,
        message,
        context,
      })
      currentSessionId.value = res.session_id
      // 先设工具调用信息，让 Vue 有机会渲染，再追加消息
      toolsInProgress.value = res.tools_called || []
      await new Promise(resolve => setTimeout(resolve, 0))
      messages.value.push({
        role: 'assistant',
        content: res.reply,
        tool_name: (res.tools_called || []).join(','),
        created_at: new Date().toISOString(),
      })
    } catch (e) {
      error.value = e.response?.data?.error || e.message || '发送失败'
      messages.value.push({
        role: 'assistant',
        content: `❌ ${error.value}`,
        created_at: new Date().toISOString(),
      })
    } finally {
      loading.value = false
    }
  }

  async function loadSession(sessionId) {
    currentSessionId.value = sessionId
    const msgs = await getSessionMessages(sessionId)
    messages.value = msgs
  }

  async function removeSession(sessionId) {
    await deleteSession(sessionId)
    if (currentSessionId.value === sessionId) {
      startNewSession()
    }
  }

  return {
    isOpen, currentSessionId, messages, loading, toolsInProgress, error,
    togglePanel, closePanel, startNewSession,
    send, loadSession, removeSession,
  }
})
