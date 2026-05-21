<template>
  <div class="scheduled-generation-tasks">
    <div class="page-header">
      <h2>{{ $t('menu.scheduledGenerationTasks') }}</h2>
      <el-button type="primary" @click="openDialog()">
        {{ $t('common.create') }}
      </el-button>
    </div>

    <el-table :data="tasks" v-loading="loading" stripe>
      <el-table-column prop="name" :label="$t('scheduledTask.name')" min-width="140" />
      <el-table-column prop="requirement_document_title" :label="$t('scheduledTask.document')" min-width="160" />
      <el-table-column prop="ai_model_config_name" :label="$t('scheduledTask.aiModel')" min-width="140" />
      <el-table-column prop="scheduled_time" :label="$t('scheduledTask.scheduledTime')" width="100" />
      <el-table-column :label="$t('scheduledTask.status')" width="90">
        <template #default="{ row }">
          <el-switch
            v-model="row.is_active"
            @change="handleToggle(row)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="last_run_at" :label="$t('scheduledTask.lastRunAt')" width="160">
        <template #default="{ row }">
          {{ row.last_run_at ? formatDateTime(row.last_run_at) : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="last_run_status" :label="$t('scheduledTask.lastRunStatus')" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.last_run_status)" size="small">
            {{ row.last_run_status || '-' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('common.actions')" width="120" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openDialog(row)">{{ $t('common.edit') }}</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">{{ $t('common.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑 Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingTask ? $t('common.edit') : $t('common.create')"
      width="500px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item :label="$t('scheduledTask.name')" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="$t('scheduledTask.document')" prop="requirement_document">
          <el-select v-model="form.requirement_document" filterable style="width:100%">
            <el-option
              v-for="doc in documents"
              :key="doc.id"
              :label="doc.title"
              :value="doc.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('scheduledTask.aiModel')">
          <el-select v-model="form.ai_model_config" clearable style="width:100%">
            <el-option
              v-for="cfg in aiConfigs"
              :key="cfg.id"
              :label="cfg.name"
              :value="cfg.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('scheduledTask.scheduledTime')" prop="scheduled_time">
          <el-time-picker
            v-model="form.scheduled_time"
            format="HH:mm"
            value-format="HH:mm:ss"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item :label="$t('scheduledTask.status')">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getScheduledGenerationTasks,
  createScheduledGenerationTask,
  updateScheduledGenerationTask,
  deleteScheduledGenerationTask,
  toggleScheduledGenerationTask,
  getRequirementDocuments,
  getAIModelConfigs,
} from '@/api/requirement-analysis'

const tasks = ref([])
const loading = ref(false)
const documents = ref([])
const aiConfigs = ref([])
const dialogVisible = ref(false)
const editingTask = ref(null)
const submitting = ref(false)
const formRef = ref(null)

const defaultForm = () => ({
  name: '',
  requirement_document: null,
  ai_model_config: null,
  scheduled_time: '02:00:00',
  is_active: true,
})
const form = ref(defaultForm())

const rules = {
  name: [{ required: true, message: '请填写任务名称', trigger: 'blur' }],
  requirement_document: [{ required: true, message: '请选择需求文档', trigger: 'change' }],
  scheduled_time: [{ required: true, message: '请选择执行时间', trigger: 'change' }],
}

async function fetchTasks() {
  loading.value = true
  try {
    const res = await getScheduledGenerationTasks()
    tasks.value = res.data?.results ?? res.data ?? []
  } finally {
    loading.value = false
  }
}

async function fetchOptions() {
  const [docRes, cfgRes] = await Promise.all([
    getRequirementDocuments(),
    getAIModelConfigs({ role: 'writer' }),
  ])
  documents.value = docRes.data?.results ?? docRes.data ?? []
  aiConfigs.value = cfgRes.data?.results ?? cfgRes.data ?? []
}

function openDialog(task = null) {
  editingTask.value = task
  form.value = task
    ? { ...task }
    : defaultForm()
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    if (editingTask.value) {
      await updateScheduledGenerationTask(editingTask.value.id, form.value)
    } else {
      await createScheduledGenerationTask(form.value)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    fetchTasks()
  } finally {
    submitting.value = false
  }
}

async function handleToggle(row) {
  try {
    await toggleScheduledGenerationTask(row.id)
  } catch {
    row.is_active = !row.is_active
    ElMessage.error('切换失败')
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm('确认删除该定时任务？', '提示', { type: 'warning' })
  await deleteScheduledGenerationTask(row.id)
  ElMessage.success('已删除')
  fetchTasks()
}

function statusTagType(status) {
  return { success: 'success', failed: 'danger', running: 'warning', pending: 'info' }[status] || 'info'
}

function formatDateTime(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : ''
}

onMounted(() => {
  fetchTasks()
  fetchOptions()
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
</style>
