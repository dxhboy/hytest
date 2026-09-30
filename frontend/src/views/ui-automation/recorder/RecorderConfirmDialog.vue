<template>
  <!-- 录制确认弹窗：步骤列表 + 元素匹配结果 + 编辑/保存 -->
  <el-dialog
    v-model="visible"
    :title="$t('uiAutomation.recorder.confirmTitle')"
    width="800px"
    :close-on-click-modal="false"
  >
    <el-form :model="form" label-position="top" style="margin-bottom: 16px;">
      <el-form-item :label="$t('uiAutomation.recorder.testCaseName')" required>
        <el-input v-model="form.testCaseName" :placeholder="$t('uiAutomation.recorder.testCaseNamePlaceholder')" />
      </el-form-item>
    </el-form>

    <el-table :data="editableSteps" border size="small" max-height="400">
      <el-table-column type="index" label="#" width="50" />
      <el-table-column :label="$t('uiAutomation.recorder.actionType')" width="100">
        <template #default="{ row }">
          <el-tag :type="actionTagType(row.action_type)" size="small">{{ row.action_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('uiAutomation.recorder.elementName')" min-width="180">
        <template #default="{ row }">
          <span v-if="row.status === 'no_element'" style="color: #c0c4cc;">—</span>
          <el-input
            v-else
            v-model="row.element_name"
            size="small"
            :placeholder="row.element_info?.element_name || ''"
          />
        </template>
      </el-table-column>
      <el-table-column :label="$t('uiAutomation.recorder.matchStatus')" width="140">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'reused'" type="success" size="small">{{ $t('uiAutomation.recorder.statusReused') }}</el-tag>
          <el-tag v-else-if="row.status === 'updated'" type="warning" size="small">{{ $t('uiAutomation.recorder.statusUpdated') }}</el-tag>
          <el-tag v-else-if="row.status === 'created'" type="primary" size="small">{{ $t('uiAutomation.recorder.statusCreated') }}</el-tag>
          <el-tag v-else size="small" type="info">—</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('uiAutomation.recorder.inputValue')" min-width="100">
        <template #default="{ row }">
          <span v-if="row.input_value">"{{ row.input_value }}"</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('uiAutomation.recorder.actions')" width="80" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeStep($index)">
            {{ $t('uiAutomation.recorder.delete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="visible = false">{{ $t('uiAutomation.recorder.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" :disabled="!form.testCaseName" @click="onConfirm">
        {{ $t('uiAutomation.recorder.saveTestCase') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  matchResults: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const visible = ref(false)
const saving = ref(false)
const form = ref({ testCaseName: '' })
const editableSteps = ref([])

watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { emit('update:modelValue', val) })
watch(() => props.matchResults, (results) => {
  editableSteps.value = results.map(r => ({
    ...r,
    element_name: r.element_name || r.element_info?.element_name || '',
  }))
}, { immediate: true })

function actionTagType(action) {
  const map = { click: 'primary', fill: 'success', hover: 'info', scroll: 'warning' }
  return map[action] || ''
}

function removeStep(index) {
  editableSteps.value.splice(index, 1)
  // 重新编号
  editableSteps.value.forEach((s, i) => { s.step_number = i + 1 })
}

async function onConfirm() {
  saving.value = true
  emit('confirm', {
    testCaseName: form.value.testCaseName,
    steps: editableSteps.value,
  })
}

defineExpose({ resetSaving: () => { saving.value = false } })
</script>
