<template>
  <div class="tool-indicator" v-if="tools.length">
    <el-icon class="spinning"><Loading /></el-icon>
    <span>{{ $t('aiAssistant.executing') }}: {{ tools.join(', ') }}</span>
  </div>
  <div class="tool-indicator thinking" v-else-if="loading">
    <el-icon class="spinning"><Loading /></el-icon>
    <span>{{ $t('aiAssistant.thinking') }}</span>
  </div>
</template>

<script setup>
import { Loading } from '@element-plus/icons-vue'
defineProps({
  tools: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
</script>

<style scoped>
.tool-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
  padding: 6px 12px;
}
.thinking {
  font-style: italic;
}
.spinning {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
