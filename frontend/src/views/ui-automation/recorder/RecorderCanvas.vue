<template>
  <!-- 投屏画布：渲染 Playwright 截图帧，捕获用户操作事件 -->
  <div class="recorder-canvas-wrapper" ref="wrapperRef">
    <canvas
      ref="canvasRef"
      :width="viewportWidth"
      :height="viewportHeight"
      class="recorder-canvas"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @wheel.prevent="onWheel"
      @contextmenu.prevent
      tabindex="0"
      @keydown="onKeyDown"
    />
    <!-- 文本输入浮层：点击输入框元素后弹出 -->
    <div v-if="showInputOverlay" class="input-overlay" :style="inputOverlayStyle">
      <el-input
        ref="inputRef"
        v-model="inputText"
        :placeholder="$t('recorder.inputPlaceholder')"
        @keydown.enter="submitInput"
        @keydown.esc="cancelInput"
        autofocus
      />
      <div class="input-actions">
        <el-button size="small" type="primary" @click="submitInput">{{ $t('recorder.confirm') }}</el-button>
        <el-button size="small" @click="cancelInput">{{ $t('recorder.cancel') }}</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  viewportWidth: { type: Number, default: 1280 },
  viewportHeight: { type: Number, default: 720 },
})

const emit = defineEmits(['mousedown', 'mousemove', 'scroll', 'keydown', 'input'])

const canvasRef = ref(null)
const wrapperRef = ref(null)
const showInputOverlay = ref(false)
const inputText = ref('')
const inputRef = ref(null)
const inputOverlayStyle = ref({})

// 缓存 Image 对象，避免每帧创建
let frameImage = null

/**
 * 渲染一帧截图到 Canvas
 * @param {string} base64Data - JPEG base64 编码的帧数据
 */
function renderFrame(base64Data) {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')

  if (!frameImage) {
    frameImage = new Image()
    frameImage.onload = () => {
      ctx.drawImage(frameImage, 0, 0, canvas.width, canvas.height)
    }
  }
  frameImage.src = `data:image/jpeg;base64,${base64Data}`
}

/**
 * 将 Canvas 上的鼠标坐标映射到 Playwright viewport 坐标
 */
function mapCoordinates(event) {
  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  const scaleX = props.viewportWidth / rect.width
  const scaleY = props.viewportHeight / rect.height
  return {
    x: Math.round((event.clientX - rect.left) * scaleX),
    y: Math.round((event.clientY - rect.top) * scaleY),
  }
}

function onMouseDown(event) {
  const { x, y } = mapCoordinates(event)
  const button = event.button === 2 ? 'right' : 'left'
  emit('mousedown', { x, y, button })
}

function onMouseMove(event) {
  // 节流：每 50ms 最多发一次
  if (onMouseMove._throttled) return
  onMouseMove._throttled = true
  setTimeout(() => { onMouseMove._throttled = false }, 50)

  const { x, y } = mapCoordinates(event)
  emit('mousemove', { x, y })
}

function onWheel(event) {
  const { x, y } = mapCoordinates(event)
  emit('scroll', { x, y, deltaX: event.deltaX, deltaY: event.deltaY })
}

function onKeyDown(event) {
  emit('keydown', { key: event.key, modifiers: {
    ctrl: event.ctrlKey,
    shift: event.shiftKey,
    alt: event.altKey,
    meta: event.metaKey,
  }})
}

/**
 * 弹出文本输入浮层（由父组件调用，当检测到点击的是输入框类元素时）
 */
function showInput(x, y) {
  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  const scaleX = rect.width / props.viewportWidth
  const scaleY = rect.height / props.viewportHeight
  inputOverlayStyle.value = {
    left: `${x * scaleX}px`,
    top: `${y * scaleY}px`,
  }
  inputText.value = ''
  showInputOverlay.value = true
  nextTick(() => inputRef.value?.focus())
}

function submitInput() {
  if (inputText.value) {
    emit('input', { text: inputText.value })
  }
  showInputOverlay.value = false
}

function cancelInput() {
  showInputOverlay.value = false
}

// 暴露方法给父组件
defineExpose({ renderFrame, showInput })
</script>

<style scoped>
.recorder-canvas-wrapper {
  position: relative;
  display: inline-block;
  background: #1a1a1a;
  border-radius: 4px;
  overflow: hidden;
}
.recorder-canvas {
  display: block;
  max-width: 100%;
  height: auto;
  cursor: crosshair;
  outline: none;
}
.input-overlay {
  position: absolute;
  z-index: 10;
  background: white;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  padding: 8px;
  min-width: 200px;
}
.input-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
  justify-content: flex-end;
}
</style>
