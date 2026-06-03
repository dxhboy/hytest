<template>
  <div class="jira-import-page" style="padding: 24px">
    <div class="page-header" style="margin-bottom: 20px">
      <h2>{{ $t('requirementAnalysis.jira.importTitle') }}</h2>
      <p style="color: #909399">{{ $t('requirementAnalysis.jira.importDesc') }}</p>
    </div>

    <el-steps :active="currentStep" finish-status="success" style="margin-bottom: 32px">
      <el-step :title="$t('requirementAnalysis.jira.step1')" />
      <el-step :title="$t('requirementAnalysis.jira.step2')" />
      <el-step :title="$t('requirementAnalysis.jira.step3')" />
    </el-steps>

    <!-- Step 1: 输入 URL -->
    <div v-if="currentStep === 0">
      <el-card style="margin-bottom: 16px">
        <template #header>{{ $t('requirementAnalysis.jira.inputUrls') }}</template>
        <el-radio-group v-model="inputMode" style="margin-bottom: 12px">
          <el-radio value="single">{{ $t('requirementAnalysis.jira.singleMode') }}</el-radio>
          <el-radio value="batch">{{ $t('requirementAnalysis.jira.batchMode') }}</el-radio>
        </el-radio-group>

        <el-input v-if="inputMode === 'single'" v-model="singleUrl"
                  :placeholder="$t('requirementAnalysis.jira.urlPlaceholder')"
                  style="margin-bottom: 8px" />
        <el-input v-else v-model="batchUrls" type="textarea" :rows="6"
                  :placeholder="$t('requirementAnalysis.jira.batchPlaceholder')" />

        <el-checkbox v-model="expandEpic" style="margin-top: 8px">
          {{ $t('requirementAnalysis.jira.expandEpic') }}
        </el-checkbox>

        <div style="margin-top: 16px; display: flex; align-items: center; gap: 8px">
          <span>{{ $t('requirementAnalysis.jira.bindVersion') }}</span>
          <el-select v-model="selectedVersionId" clearable style="width: 240px"
                     :placeholder="$t('requirementAnalysis.jira.selectVersion')">
            <el-option v-for="v in versions" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
        </div>
      </el-card>

      <el-button type="primary" @click="goPreview" :loading="previewing">
        {{ $t('requirementAnalysis.jira.preview') }}
      </el-button>
    </div>

    <!-- Step 2: 字段选择 + 预览结果 -->
    <div v-if="currentStep === 1">
      <el-card style="margin-bottom: 16px">
        <template #header>{{ $t('requirementAnalysis.jira.selectFields') }}</template>
        <el-checkbox-group v-model="selectedFields">
          <el-checkbox value="summary" disabled>Summary（必选）</el-checkbox>
          <el-checkbox value="description">Description</el-checkbox>
          <el-checkbox value="acceptance_criteria">Acceptance Criteria</el-checkbox>
          <el-checkbox value="subtasks">子任务列表</el-checkbox>
          <el-checkbox value="priority">优先级</el-checkbox>
          <el-checkbox value="labels">标签</el-checkbox>
        </el-checkbox-group>
      </el-card>

      <el-card style="margin-bottom: 16px">
        <template #header>{{ $t('requirementAnalysis.jira.previewResults') }}</template>
        <div v-for="(item, idx) in previewResults" :key="idx" style="margin-bottom: 12px">
          <el-alert v-if="!item.success" :title="item.error || '拉取失败'" type="error" show-icon />
          <el-card v-else shadow="never" style="background: #f8f9fa">
            <div style="font-weight: bold">{{ item.issue_key }}: {{ item.summary }}</div>
            <div style="color: #606266; font-size: 13px; margin-top: 4px; white-space: pre-wrap">
              {{ item.content_preview }}
            </div>
          </el-card>
        </div>
      </el-card>

      <el-button @click="currentStep = 0">返回</el-button>
      <el-button type="primary" @click="currentStep = 2">下一步</el-button>
    </div>

    <!-- Step 3: 生成 -->
    <div v-if="currentStep === 2">
      <el-card style="margin-bottom: 16px">
        <template #header>{{ $t('requirementAnalysis.jira.aiConfig') }}</template>
        <el-form label-width="120px">
          <el-form-item :label="$t('requirementAnalysis.jira.writerModel')">
            <el-select v-model="writerModelId" clearable style="width: 300px">
              <el-option v-for="m in aiModels.filter(m => m.role === 'writer')"
                         :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('requirementAnalysis.jira.reviewerModel')">
            <el-select v-model="reviewerModelId" clearable style="width: 300px">
              <el-option v-for="m in aiModels.filter(m => m.role === 'reviewer')"
                         :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </el-form-item>
        </el-form>
      </el-card>

      <el-button @click="currentStep = 1">返回</el-button>
      <el-button type="primary" @click="startImport" :loading="importing">
        {{ $t('requirementAnalysis.jira.startGenerate') }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { previewJiraIssues, importJiraIssues } from '@/api/jira'
import request from '@/utils/api'

const { t } = useI18n()
const router = useRouter()

const currentStep = ref(0)
const inputMode = ref('single')
const singleUrl = ref('')
const batchUrls = ref('')
const expandEpic = ref(false)
const selectedVersionId = ref(null)
const selectedFields = ref(['summary', 'description'])
const previewing = ref(false)
const importing = ref(false)
const previewResults = ref([])
const versions = ref([])
const aiModels = ref([])
const writerModelId = ref(null)
const reviewerModelId = ref(null)

const getUrls = () => {
  if (inputMode.value === 'single') {
    return singleUrl.value ? [singleUrl.value.trim()] : []
  }
  return batchUrls.value.split('\n').map(u => u.trim()).filter(Boolean)
}

const goPreview = async () => {
  const urls = getUrls()
  if (!urls.length) {
    ElMessage.warning(t('requirementAnalysis.jira.urlRequired'))
    return
  }
  previewing.value = true
  try {
    const res = await previewJiraIssues({ urls, selected_fields: selectedFields.value })
    previewResults.value = res.data.results
    currentStep.value = 1
  } catch {
    ElMessage.error(t('requirementAnalysis.jira.previewFailed'))
  } finally {
    previewing.value = false
  }
}

const startImport = async () => {
  importing.value = true
  try {
    const res = await importJiraIssues({
      urls: getUrls(),
      selected_fields: selectedFields.value,
      version_id: selectedVersionId.value,
      writer_model_config_id: writerModelId.value,
      reviewer_model_config_id: reviewerModelId.value,
      expand_epic: expandEpic.value,
    })
    ElMessage.success(t('requirementAnalysis.jira.importSuccess'))
    router.push(`/ai-generation/task-detail/${res.data.task_id}`)
  } catch {
    ElMessage.error(t('requirementAnalysis.jira.importFailed'))
  } finally {
    importing.value = false
  }
}

onMounted(async () => {
  try {
    const [vRes, mRes] = await Promise.all([
      request({ url: '/versions/', method: 'get' }),
      request({ url: '/requirement-analysis/ai-models/', method: 'get' }),
    ])
    versions.value = vRes.data.results || vRes.data
    aiModels.value = mRes.data.results || mRes.data
  } catch {}
})
</script>
