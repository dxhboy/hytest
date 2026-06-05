<template>
  <div class="knowledge-base">
    <!-- 顶部：项目选择 -->
    <div class="kb-header">
      <el-select
        v-model="selectedProjectId"
        :placeholder="$t('knowledgeBase.selectProjectPlaceholder')"
        filterable
        style="width: 280px"
        @change="onProjectChange"
      >
        <el-option
          v-for="p in projects"
          :key="p.id"
          :label="p.name"
          :value="p.id"
        />
      </el-select>
    </div>

    <!-- 主内容：Tab 切换 -->
    <el-tabs v-if="selectedProjectId" v-model="activeTab" class="kb-tabs">
      <!-- Tab 1: 知识库文档 -->
      <el-tab-pane :label="$t('knowledgeBase.tabDocs')" name="docs">
        <div class="tab-toolbar">
          <span class="doc-count">{{ documents.length }} 个文档</span>
          <el-upload
            :show-file-list="false"
            :before-upload="handleBeforeUpload"
            :http-request="handleUpload"
            accept=".pdf,.docx,.md,.txt"
          >
            <el-button type="primary" :loading="uploading">
              + {{ $t('knowledgeBase.uploadBtn') }}
            </el-button>
          </el-upload>
        </div>

        <el-table :data="documents" stripe style="width: 100%">
          <el-table-column :label="$t('knowledgeBase.colName')" prop="name" min-width="200" />
          <el-table-column :label="$t('knowledgeBase.colSize')" width="100">
            <template #default="{ row }">
              {{ formatSize(row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('knowledgeBase.colStatus')" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ $t(`knowledgeBase.status${capitalize(row.status)}`) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('knowledgeBase.colAction')" width="80">
            <template #default="{ row }">
              <el-popconfirm
                :title="$t('knowledgeBase.deleteConfirm')"
                @confirm="handleDelete(row.id)"
              >
                <template #reference>
                  <el-button type="danger" link size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="documents.length === 0 && !docsLoading" class="empty-hint">
          <el-empty description="暂无文档，请上传" :image-size="80" />
        </div>
      </el-tab-pane>

      <!-- Tab 2: Skills 配置 -->
      <el-tab-pane :label="$t('knowledgeBase.tabSkills')" name="skills">
        <div class="skills-hint">{{ $t('knowledgeBase.skillsHint') }}</div>

        <el-input
          v-model="skillContent"
          type="textarea"
          :autosize="{ minRows: 12, maxRows: 30 }"
          :placeholder="$t('knowledgeBase.skillsPlaceholder')"
          class="skills-editor"
        />

        <div class="skills-footer">
          <span v-if="skillSavedAt" class="saved-time">
            {{ $t('knowledgeBase.lastSaved') }}{{ skillSavedAt }}
          </span>
          <div class="skills-actions">
            <el-button @click="showPreview = true">{{ $t('knowledgeBase.previewBtn') }}</el-button>
            <el-button type="primary" :loading="skillSaving" @click="handleSaveSkill">
              {{ $t('knowledgeBase.saveBtn') }}
            </el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <div v-if="!selectedProjectId" class="select-hint">
      <el-empty description="请先选择项目" :image-size="80" />
    </div>

    <!-- Skills 预览弹窗 -->
    <el-dialog
      v-model="showPreview"
      :title="$t('knowledgeBase.previewTitle')"
      width="600px"
    >
      <pre class="skills-preview">{{ skillContent || '（暂无内容）' }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import {
  getKnowledgeDocs,
  uploadKnowledgeDoc,
  deleteKnowledgeDoc,
  getProjectSkill,
  saveProjectSkill,
} from '@/api/knowledge'
import request from '@/utils/api'

const { t } = useI18n()

const projects = ref([])
const selectedProjectId = ref(null)
const activeTab = ref('docs')

// 文档列表
const documents = ref([])
const docsLoading = ref(false)
const uploading = ref(false)

// Skills
const skillContent = ref('')
const skillSaving = ref(false)
const skillSavedAt = ref('')
const showPreview = ref(false)
const activeTimers = []

onMounted(async () => {
  try {
    const res = await request({ url: '/projects/list/', method: 'get' })
    projects.value = res.data?.results || []
  } catch (e) {
    // 静默失败，projects 为空
  }
})

async function onProjectChange(projectId) {
  if (!projectId) return
  await Promise.all([loadDocs(projectId), loadSkill(projectId)])
}

async function loadDocs(projectId) {
  docsLoading.value = true
  try {
    const res = await getKnowledgeDocs(projectId)
    documents.value = res.results || []
  } finally {
    docsLoading.value = false
  }
}

async function loadSkill(projectId) {
  try {
    const res = await getProjectSkill(projectId)
    skillContent.value = res.content || ''
    skillSavedAt.value = res.updated_at
      ? new Date(res.updated_at).toLocaleString()
      : ''
  } catch (e) {
    skillContent.value = ''
  }
}

function handleBeforeUpload(file) {
  const allowed = ['.pdf', '.docx', '.md', '.txt']
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.error(t('knowledgeBase.uploadHint'))
    return false
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error(t('knowledgeBase.uploadHint'))
    return false
  }
  return true
}

async function handleUpload({ file }) {
  uploading.value = true
  try {
    const res = await uploadKnowledgeDoc(selectedProjectId.value, file)
    documents.value.unshift(res)
    ElMessage.success(t('knowledgeBase.uploadSuccess'))
    pollDocStatus(res.id)
  } catch (e) {
    ElMessage.error(t('knowledgeBase.uploadFailed'))
  } finally {
    uploading.value = false
  }
}

function pollDocStatus(docId) {
  let retries = 0
  const timer = setInterval(async () => {
    retries++
    if (retries > 30) { clearInterval(timer); return }
    try {
      const res = await getKnowledgeDocs(selectedProjectId.value)
      const doc = (res.results || []).find(d => d.id === docId)
      if (doc) {
        const idx = documents.value.findIndex(d => d.id === docId)
        if (idx !== -1) Object.assign(documents.value[idx], doc)
        if (doc.status === 'indexed' || doc.status === 'failed') {
          clearInterval(timer)
        }
      }
    } catch (e) {
      clearInterval(timer)
    }
  }, 2000)
  activeTimers.push(timer)
}

async function handleDelete(docId) {
  try {
    await deleteKnowledgeDoc(docId)
    documents.value = documents.value.filter(d => d.id !== docId)
    ElMessage.success(t('knowledgeBase.deleteSuccess'))
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function handleSaveSkill() {
  skillSaving.value = true
  try {
    const res = await saveProjectSkill(selectedProjectId.value, skillContent.value)
    skillSavedAt.value = new Date(res.updated_at).toLocaleString()
    ElMessage.success(t('knowledgeBase.saveSuccess'))
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    skillSaving.value = false
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function statusTagType(status) {
  const map = { pending: 'info', processing: 'warning', indexed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1)
}

onBeforeUnmount(() => {
  activeTimers.forEach(clearInterval)
})
</script>

<style scoped>
.knowledge-base {
  padding: 20px;
}
.kb-header {
  margin-bottom: 20px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.doc-count {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.empty-hint {
  margin-top: 40px;
}
.skills-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.6;
}
.skills-editor {
  font-family: monospace;
}
.skills-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
.saved-time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.skills-actions {
  display: flex;
  gap: 8px;
}
.select-hint {
  margin-top: 60px;
}
.skills-preview {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: monospace;
  font-size: 13px;
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
}
</style>