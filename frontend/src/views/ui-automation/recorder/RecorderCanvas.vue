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
      @paste.prevent="onPaste"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  viewportWidth: { type: Number, default: 1280 },
  viewportHeight: { type: Number, default: 720 },
})

const emit = defineEmits(['mousedown', 'mousemove', 'scroll', 'keydown', 'paste'])

const canvasRef = ref(null)
const wrapperRef = ref(null)

let frameImage = null
let pendingFrame = null
let rafId = 0

function renderFrame(base64Data) {
  pendingFrame = base64Data
  if (!rafId) {
    rafId = requestAnimationFrame(drawFrame)
  }
}

function drawFrame() {
  rafId = 0
  if (!pendingFrame) return
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')

  if (!frameImage) {
    frameImage = new Image()
    frameImage.onload = () => {
      ctx.drawImage(frameImage, 0, 0, canvas.width, canvas.height)
    }
  }
  frameImage.src = `data:image/jpeg;base64,${pendingFrame}`
  pendingFrame = null
}

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
  // 点击后让 canvas 获取焦点，确保后续键盘事件能被捕获
  canvasRef.value?.focus()
  const { x, y } = mapCoordinates(event)
  const button = event.button === 2 ? 'right' : 'left'
  emit('mousedown', { x, y, button })
}

function onMouseMove(event) {
  if (onMouseMove._throttled) return
  onMouseMove._throttled = true
  setTimeout(() => { onMouseMove._throttled = false }, 150)

  const { x, y } = mapCoordinates(event)
  emit('mousemove', { x, y })
}

function onWheel(event) {
  if (onWheel._throttled) return
  onWheel._throttled = true
  setTimeout(() => { onWheel._throttled = false }, 100)

  const { x, y } = mapCoordinates(event)
  emit('scroll', { x, y, deltaX: event.deltaX, deltaY: event.deltaY })
}

function onKeyDown(event) {
  // Ctrl+V / Cmd+V 放行给 paste 事件处理
  if ((event.ctrlKey || event.metaKey) && event.key === 'v') return
  event.preventDefault()
  emit('keydown', { key: event.key, modifiers: {
    ctrl: event.ctrlKey,
    shift: event.shiftKey,
    alt: event.altKey,
    meta: event.metaKey,
  }})
}

function onPaste(event) {
  const text = event.clipboardData?.getData('text/plain')
  if (text) {
    emit('paste', { text })
  }
}

defineExpose({ renderFrame })
</script>

<style scoped>
.recorder-canvas-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  background: #fff;
  border-radius: 4px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
}
.recorder-canvas {
  display: block;
  max-width: 100%;
  max-height: 100%;
  cursor: default;
  outline: none;
}
</style>
