<template>
  <!-- 实时步骤列表：录制过程中每个操作实时追加，连续滚动自动折叠 -->
  <div class="step-list">
    <div class="step-list-header">
      <h4>{{ $t('uiAutomation.recorder.steps') }} ({{ steps.length }})</h4>
    </div>
    <div class="step-list-body" ref="listBody">
      <template v-for="item in displaySteps" :key="item.key">
        <!-- 折叠的连续滚动 -->
        <div v-if="item.collapsed" class="step-item step-collapsed">
          <span class="step-number">#{{ item.startNum }}-{{ item.endNum }}</span>
          <el-tag type="warning" size="small">scroll</el-tag>
          <span class="step-desc">x{{ item.count }}</span>
        </div>
        <!-- 普通步骤 -->
        <div v-else class="step-item" :class="actionClass(item.step.action_type)">
          <span class="step-number">#{{ item.step.step_number }}</span>
          <el-tag :type="actionTagType(item.step.action_type)" size="small">
            {{ item.step.action_type }}
          </el-tag>
          <span class="step-desc" :title="stepDescription(item.step)">
            {{ stepDescription(item.step) }}
          </span>
        </div>
      </template>
      <div v-if="steps.length === 0" class="empty-hint">
        {{ $t('uiAutomation.recorder.noStepsYet') }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'

const props = defineProps({
  steps: { type: Array, default: () => [] },
})

const listBody = ref(null)

// 连续 scroll 事件自动折叠为一条
const displaySteps = computed(() => {
  const result = []
  let i = 0
  while (i < props.steps.length) {
    const step = props.steps[i]
    if (step.action_type === 'scroll') {
      let j = i + 1
      while (j < props.steps.length && props.steps[j].action_type === 'scroll') j++
      const count = j - i
      if (count >= 3) {
        result.push({
          key: `scroll-${i}`,
          collapsed: true,
          count,
          startNum: props.steps[i].step_number,
          endNum: props.steps[j - 1].step_number,
        })
      } else {
        for (let k = i; k < j; k++) {
          result.push({ key: `step-${k}`, collapsed: false, step: props.steps[k] })
        }
      }
      i = j
    } else {
      result.push({ key: `step-${i}`, collapsed: false, step })
      i++
    }
  }
  return result
})

// 新步骤自动滚动到底部
watch(() => props.steps.length, () => {
  nextTick(() => {
    if (listBody.value) listBody.value.scrollTop = listBody.value.scrollHeight
  })
})

function stepDescription(step) {
  const info = step.element_info
  if (!info) return '-'
  // 优先显示文本内容，其次显示元素名
  const text = info.text_content?.slice(0, 30)
  const tag = (info.element_type || info.tag_name || '').toLowerCase()
  if (step.input_value) return `${tag} "${step.input_value}"`
  if (text) return `${tag} "${text}"`
  return info.element_name || tag || '-'
}

function actionTagType(action) {
  const map = { click: 'primary', fill: 'success', hover: 'info', scroll: 'warning' }
  return map[action] || ''
}

function actionClass(action) {
  return action === 'fill' ? 'step-fill' : ''
}
</script>

<style scoped>
.step-list {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.step-list-header {
  padding: 12px 16px;
  border-bottom: 1px solid #e4e7ed;
}
.step-list-header h4 {
  margin: 0;
  font-size: 14px;
}
.step-list-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  margin-bottom: 3px;
  background: #fafafa;
  font-size: 12px;
}
.step-item.step-fill {
  background: #f0f9eb;
}
.step-item.step-collapsed {
  background: #fdf6ec;
  color: #909399;
  font-style: italic;
}
.step-number {
  color: #909399;
  font-size: 11px;
  min-width: 24px;
  flex-shrink: 0;
}
.step-desc {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #606266;
}
.empty-hint {
  text-align: center;
  color: #c0c4cc;
  padding: 40px;
}
</style>
