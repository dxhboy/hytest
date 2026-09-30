<template>
  <!-- 录制工具栏：URL 输入、开始/停止按钮 -->
  <div class="recorder-toolbar">
    <el-input
      v-model="targetUrl"
      :placeholder="$t('uiAutomation.recorder.urlPlaceholder')"
      :disabled="isRecording"
      class="url-input"
      @keydown.enter="onNavigate"
    >
      <template #prepend>URL</template>
      <template #append>
        <el-button @click="onNavigate" :disabled="!targetUrl || isRecording">
          {{ $t('uiAutomation.recorder.go') }}
        </el-button>
      </template>
    </el-input>

    <el-select v-model="selectedProjectId" :placeholder="$t('uiAutomation.recorder.selectProject')" :disabled="isRecording" class="project-select">
      <el-option
        v-for="p in projects"
        :key="p.id"
        :label="p.name"
        :value="p.id"
      />
    </el-select>

    <div class="toolbar-actions">
      <el-button
        v-if="!isRecording"
        type="danger"
        :icon="VideoCamera"
        :disabled="!targetUrl || !selectedProjectId"
        @click="onStart"
      >
        {{ $t('uiAutomation.recorder.startRecording') }}
      </el-button>

      <el-button
        v-else
        type="warning"
        :icon="VideoPause"
        @click="onStop"
      >
        {{ $t('uiAutomation.recorder.stopRecording') }}
      </el-button>

      <el-button
        v-if="isRecording"
        @click="$emit('cancel')"
      >
        {{ $t('uiAutomation.recorder.cancel') }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { VideoCamera, VideoPause } from '@element-plus/icons-vue'
import { getUiProjects } from '@/api/ui_automation'

const props = defineProps({
  isRecording: { type: Boolean, default: false },
})

const emit = defineEmits(['start', 'stop', 'navigate', 'cancel'])

const targetUrl = ref('')
const selectedProjectId = ref(null)
const projects = ref([])

onMounted(async () => {
  try {
    const resp = await getUiProjects()
    projects.value = resp.data?.results || resp.data || []
  } catch (e) {
    console.error('加载项目列表失败', e)
  }
})

function onStart() {
  emit('start', {
    projectId: selectedProjectId.value,
    targetUrl: targetUrl.value,
  })
}

function onStop() {
  emit('stop')
}

function onNavigate() {
  if (targetUrl.value) {
    emit('navigate', targetUrl.value)
  }
}

defineExpose({ targetUrl, selectedProjectId })
</script>

<style scoped>
.recorder-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}
.url-input {
  flex: 1;
  min-width: 200px;
}
.project-select {
  width: 160px;
  flex-shrink: 0;
}
.toolbar-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
</style>
