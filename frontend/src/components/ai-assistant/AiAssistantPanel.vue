<template>
  <Teleport to="body">
    <el-tooltip :content="$t('aiAssistant.openTooltip')" placement="left">
      <el-button
        class="ai-fab"
        type="primary"
        circle
        :icon="Cpu"
        @click="store.togglePanel()"
        v-show="!store.isOpen"
      />
    </el-tooltip>

    <Transition name="panel-slide">
      <div class="ai-panel" v-show="store.isOpen">
        <AiChatWindow />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { Cpu } from '@element-plus/icons-vue'
import { useAiAssistantStore } from '@/stores/aiAssistant'
import AiChatWindow from './AiChatWindow.vue'

const store = useAiAssistantStore()
</script>

<style scoped>
.ai-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 48px;
  height: 48px;
  z-index: 2000;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.4);
}
.ai-panel {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 380px;
  height: 600px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: all 0.25s ease;
}
.panel-slide-enter-from,
.panel-slide-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}
</style>
