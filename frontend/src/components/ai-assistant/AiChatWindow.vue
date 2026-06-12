<template>
  <div class="chat-window">
    <div class="chat-header">
      <el-icon><Cpu /></el-icon>
      <span>{{ $t('aiAssistant.title') }}</span>
      <div class="header-actions">
        <el-tooltip :content="$t('aiAssistant.newSession')">
          <el-button text :icon="Plus" size="small" @click="store.startNewSession()" />
        </el-tooltip>
        <el-tooltip :content="$t('aiAssistant.close')">
          <el-button text :icon="Close" size="small" @click="store.closePanel()" />
        </el-tooltip>
      </div>
    </div>

    <div class="chat-messages" ref="messagesEl">
      <div v-if="!store.messages.length" class="empty-hint">
        <p>{{ $t('aiAssistant.hint') }}</p>
      </div>
      <AiMessageBubble v-for="(msg, i) in store.messages" :key="i" :msg="msg" />
      <AiToolCallIndicator :tools="store.toolsInProgress" :loading="store.loading" />
    </div>

    <div class="chat-input">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="2"
        :placeholder="$t('aiAssistant.placeholder')"
        :disabled="store.loading"
        resize="none"
        @keydown.enter.exact.prevent="handleSend"
      />
      <el-button
        type="primary"
        :icon="Promotion"
        circle
        :disabled="!inputText.trim() || store.loading"
        @click="handleSend"
        class="send-btn"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Cpu, Plus, Close, Promotion } from '@element-plus/icons-vue'
import { useAiAssistantStore } from '@/stores/aiAssistant'
import AiMessageBubble from './AiMessageBubble.vue'
import AiToolCallIndicator from './AiToolCallIndicator.vue'

const store = useAiAssistantStore()
const route = useRoute()
const inputText = ref('')
const messagesEl = ref(null)

const context = () => ({
  module: route.meta?.module || '',
  page: route.meta?.page || '',
  project_id: route.query?.project_id || route.params?.project_id || null,
})

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || store.loading) return
  inputText.value = ''
  await store.send(text, context())
}

watch(
  () => store.messages.length,
  async () => {
    await nextTick()
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  }
)
</script>

<style scoped>
.chat-window {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.chat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
  font-size: 14px;
}
.header-actions {
  margin-left: auto;
  display: flex;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 0;
}
.empty-hint {
  text-align: center;
  color: #c0c4cc;
  font-size: 13px;
  padding-top: 40px;
}
.chat-input {
  padding: 10px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.chat-input .el-textarea {
  flex: 1;
}
.send-btn {
  flex-shrink: 0;
}
</style>
