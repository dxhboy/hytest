<template>
  <!-- 实时步骤列表：录制过程中每个操作实时追加 -->
  <div class="step-list">
    <div class="step-list-header">
      <h4>{{ $t('recorder.steps') }} ({{ steps.length }})</h4>
    </div>
    <div class="step-list-body">
      <div v-for="step in steps" :key="step.step_number" class="step-item">
        <span class="step-number">#{{ step.step_number }}</span>
        <el-tag :type="actionTagType(step.action_type)" size="small">
          {{ step.action_type }}
        </el-tag>
        <span class="step-target" :title="step.element_info?.element_name || ''">
          {{ step.element_info?.element_name || '(no element)' }}
        </span>
        <span v-if="step.input_value" class="step-value">
          "{{ step.input_value }}"
        </span>
      </div>
      <div v-if="steps.length === 0" class="empty-hint">
        {{ $t('recorder.noStepsYet') }}
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  steps: { type: Array, default: () => [] },
})

function actionTagType(action) {
  const map = { click: 'primary', fill: 'success', hover: 'info', scroll: 'warning' }
  return map[action] || ''
}
</script>

<style scoped>
.step-list { display: flex; flex-direction: column; height: 100%; }
.step-list-header { padding: 12px 16px; border-bottom: 1px solid #e4e7ed; }
.step-list-header h4 { margin: 0; }
.step-list-body { flex: 1; overflow-y: auto; padding: 8px; }
.step-item { display: flex; align-items: center; gap: 8px; padding: 8px; border-radius: 4px; margin-bottom: 4px; background: #fafafa; }
.step-number { color: #909399; font-size: 12px; min-width: 28px; }
.step-target { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.step-value { color: #67c23a; font-size: 12px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty-hint { text-align: center; color: #c0c4cc; padding: 40px; }
</style>
