<template>
  <!-- 脚本录制主页面 -->
  <div class="recorder-view">
    <RecorderToolbar
      :is-recording="isRecording"
      @start="handleStart"
      @stop="handleStop"
      @navigate="handleNavigate"
      @cancel="handleCancel"
    />

    <div class="recorder-body">
      <!-- 左侧：Canvas 投屏区 -->
      <div class="recorder-main">
        <div v-if="!isConnected" class="recorder-placeholder">
          <el-icon :size="64" color="#c0c4cc"><VideoCamera /></el-icon>
          <p>{{ $t('recorder.placeholderText') }}</p>
        </div>
        <RecorderCanvas
          v-show="isConnected"
          ref="canvasRef"
          :viewport-width="viewportWidth"
          :viewport-height="viewportHeight"
          @mousedown="handleMouseDown"
          @mousemove="sendWs({ type: 'mousemove', ...$event })"
          @scroll="sendWs({ type: 'scroll', ...$event })"
          @keydown="sendWs({ type: 'keydown', ...$event })"
          @input="sendWs({ type: 'input', ...$event })"
        />
      </div>

      <!-- 右侧：步骤列表 -->
      <div class="recorder-sidebar">
        <RecorderStepList :steps="recordedSteps" />
      </div>
    </div>

    <!-- 确认弹窗 -->
    <RecorderConfirmDialog
      v-model="showConfirmDialog"
      :match-results="matchResults"
      @confirm="handleConfirm"
    />
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { VideoCamera } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { startRecording, stopRecording, confirmRecording, cancelRecording } from '@/api/recording'
import RecorderCanvas from './RecorderCanvas.vue'
import RecorderToolbar from './RecorderToolbar.vue'
import RecorderStepList from './RecorderStepList.vue'
import RecorderConfirmDialog from './RecorderConfirmDialog.vue'

const router = useRouter()
const canvasRef = ref(null)

// 状态
const isRecording = ref(false)
const isConnected = ref(false)
const sessionId = ref(null)
const recordedSteps = ref([])
const matchResults = ref([])
const showConfirmDialog = ref(false)
const viewportWidth = ref(1280)
const viewportHeight = ref(720)
// 记录最后一次鼠标按下的坐标（viewport 坐标系），用于在检测到输入框元素时
// 定位文本输入浮层的弹出位置
const lastClickCoords = ref({ x: 0, y: 0 })

let ws = null

// ---- WebSocket 管理 ----

function connectWebSocket(wsPath) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}${wsPath}`
  ws = new WebSocket(url)

  ws.onopen = () => {
    isConnected.value = true
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    handleWsMessage(data)
  }

  ws.onclose = () => {
    isConnected.value = false
  }

  ws.onerror = (err) => {
    console.error('WebSocket 连接错误', err)
    ElMessage.error('WebSocket 连接失败')
  }
}

function sendWs(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data))
  }
}

function handleWsMessage(data) {
  switch (data.type) {
    case 'frame':
      // 渲染截图帧到 Canvas
      canvasRef.value?.renderFrame(data.data)
      break
    case 'action':
      // 实时追加录制步骤
      recordedSteps.value.push(data.data)
      // 如果点击的是输入框类元素，弹出文本输入浮层，方便用户输入文本
      if (data.data.action_type === 'click' && data.data.element_info?.element_type === 'INPUT') {
        canvasRef.value?.showInput(lastClickCoords.value.x, lastClickCoords.value.y)
      }
      break
    case 'status':
      // 状态更新（navigating, ready, error）
      if (data.data === 'error') {
        ElMessage.error('浏览器出现错误')
      }
      break
    case 'recording_stopped':
      // 录制已停止，请求匹配结果
      handleRecordingStopped()
      break
  }
}

// ---- 操作处理 ----

async function handleStart({ projectId, targetUrl }) {
  try {
    const resp = await startRecording({
      project_id: projectId,
      target_url: targetUrl,
      viewport_width: viewportWidth.value,
      viewport_height: viewportHeight.value,
    })
    sessionId.value = resp.data.session_id
    isRecording.value = true
    recordedSteps.value = []
    connectWebSocket(resp.data.ws_path)
  } catch (e) {
    ElMessage.error('启动录制失败: ' + (e.response?.data?.error || e.message))
  }
}

function handleMouseDown(event) {
  // 先记录本次点击坐标，供后续 action 消息判断是否需要弹出文本输入浮层
  lastClickCoords.value = { x: event.x, y: event.y }
  sendWs({ type: 'mousedown', ...event })
}

async function handleStop() {
  // 通知后端停止（通过 WebSocket 控制命令）
  sendWs({ type: 'control', action: 'stop' })
}

async function handleRecordingStopped() {
  try {
    const resp = await stopRecording(sessionId.value)
    matchResults.value = resp.data.match_results || []
    isRecording.value = false
    showConfirmDialog.value = true
  } catch (e) {
    ElMessage.error('停止录制失败')
  }
}

function handleNavigate(url) {
  sendWs({ type: 'control', action: 'navigate', url })
}

async function handleCancel() {
  if (sessionId.value) {
    await cancelRecording(sessionId.value)
  }
  cleanup()
  ElMessage.info('录制已取消')
}

async function handleConfirm({ testCaseName, steps }) {
  try {
    const resp = await confirmRecording(sessionId.value, {
      test_case_name: testCaseName,
      steps,
    })
    ElMessage.success(`测试用例「${resp.data.test_case_name}」已保存，共 ${resp.data.step_count} 步`)
    showConfirmDialog.value = false
    cleanup()
    // 跳转到测试用例管理页面
    router.push('/ui-automation/test-cases')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.error || e.message))
  }
}

function cleanup() {
  if (ws) {
    ws.close()
    ws = null
  }
  isRecording.value = false
  isConnected.value = false
  sessionId.value = null
  recordedSteps.value = []
}

onUnmounted(cleanup)
</script>

<style scoped>
.recorder-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.recorder-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.recorder-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1a1a1a;
  min-height: 500px;
}
.recorder-placeholder {
  text-align: center;
  color: #c0c4cc;
}
.recorder-placeholder p {
  margin-top: 16px;
  font-size: 14px;
}
.recorder-sidebar {
  width: 350px;
  border-left: 1px solid #e4e7ed;
  background: #fff;
}
</style>
