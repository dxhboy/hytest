<template>
  <div class="project-center">
    <div class="page-header">
      <h1>{{ $t("projectCenter.title") }}</h1>
      <p>{{ $t("projectCenter.subtitle") }}</p>
    </div>

    <el-tabs v-model="activeTab" class="project-tabs">
      <!-- ========== Tab 1: AI 用例生成项目 ========== -->
      <el-tab-pane :label="$t('projectCenter.aiGeneration')" name="ai">
        <div class="tab-toolbar">
          <el-input
            v-model="ai.search"
            :placeholder="$t('projectCenter.searchPlaceholder')"
            clearable
            style="width: 240px"
            @input="() => { ai.page = 1; loadAiProjects() }"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select
            v-model="ai.statusFilter"
            :placeholder="$t('projectCenter.statusFilter')"
            clearable
            style="width: 140px"
            @change="() => { ai.page = 1; loadAiProjects() }"
          >
            <el-option :label="$t('project.active')" value="active" />
            <el-option :label="$t('project.paused')" value="paused" />
            <el-option :label="$t('project.completed')" value="completed" />
            <el-option :label="$t('project.archived')" value="archived" />
          </el-select>
          <el-button type="primary" @click="openAiDialog()">
            <el-icon><Plus /></el-icon>{{ $t("projectCenter.newProject") }}
          </el-button>
        </div>

        <el-table :data="ai.list" v-loading="ai.loading" style="width:100%">
          <el-table-column prop="name" :label="$t('project.projectName')" min-width="180">
            <template #default="{ row }">
              <el-link type="primary" @click="$router.push(`/ai-generation/projects/${row.id}`)">{{ row.name }}</el-link>
            </template>
          </el-table-column>
          <el-table-column prop="description" :label="$t('project.description')" min-width="240" show-overflow-tooltip />
          <el-table-column prop="status" :label="$t('project.status')" width="110">
            <template #default="{ row }">
              <el-tag :type="aiStatusType(row.status)">{{ aiStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner.username" :label="$t('project.owner')" width="120" />
          <el-table-column prop="created_at" :label="$t('project.createdAt')" width="170">
            <template #default="{ row }">{{ fmt(row.created_at) }}</template>
          </el-table-column>
          <el-table-column :label="$t('project.actions')" width="140" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openAiDialog(row)">{{ $t('common.edit') }}</el-button>
              <el-button size="small" type="danger" @click="deleteAiProject(row)">{{ $t('common.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="ai.page" :page-size="ai.pageSize" :total="ai.total"
          layout="total, prev, pager, next" class="pagination"
          @current-change="loadAiProjects"
        />
      </el-tab-pane>

      <!-- ========== Tab 2: 接口测试项目 ========== -->
      <el-tab-pane :label="$t('projectCenter.apiTesting')" name="api">
        <div class="tab-toolbar">
          <el-button type="primary" @click="openApiDialog()">
            <el-icon><Plus /></el-icon>{{ $t("projectCenter.newProject") }}
          </el-button>
        </div>

        <el-table :data="api.list" v-loading="api.loading" style="width:100%">
          <el-table-column prop="name" :label="$t('apiTesting.project.projectName')" min-width="180" />
          <el-table-column prop="project_type" :label="$t('apiTesting.project.projectType')" width="110">
            <template #default="{ row }">
              <el-tag :type="row.project_type === 'HTTP' ? 'primary' : 'success'">{{ row.project_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" :label="$t('apiTesting.project.projectStatus')" width="110">
            <template #default="{ row }">
              <el-tag :type="apiStatusType(row.status)">{{ apiStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner.username" :label="$t('apiTesting.project.owner')" width="120" />
          <el-table-column prop="visibility" :label="$t('apiTesting.common.visibility')" width="110">
            <template #default="{ row }">
              <el-tag :type="row.visibility === 'all' ? 'primary' : 'info'" size="small">
                {{ row.visibility === 'all' ? $t('apiTesting.common.visibleAll') : $t('apiTesting.common.visibleSelf') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="start_date" :label="$t('apiTesting.project.startDate')" width="110" />
          <el-table-column prop="end_date" :label="$t('apiTesting.project.endDate')" width="110" />
          <el-table-column :label="$t('apiTesting.common.operation')" width="160" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openApiDialog(row)">{{ $t('apiTesting.common.edit') }}</el-button>
              <el-button link type="primary" @click="viewApiProject(row)">{{ $t('apiTesting.common.view') }}</el-button>
              <el-button link type="danger" @click="deleteApiProject(row)">{{ $t('apiTesting.common.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="api.page" v-model:page-size="api.pageSize"
          :page-sizes="[10,20,50]" :total="api.total"
          layout="total, sizes, prev, pager, next" class="pagination"
          @size-change="loadApiProjects" @current-change="loadApiProjects"
        />
      </el-tab-pane>

      <!-- ========== Tab 3: UI 自动化项目 ========== -->
      <el-tab-pane :label="$t('projectCenter.uiAutomation')" name="ui">
        <div class="tab-toolbar">
          <el-input
            v-model="ui.search"
            :placeholder="$t('projectCenter.searchPlaceholder')"
            clearable
            style="width: 240px"
            @input="() => { ui.page = 1; loadUiProjects() }"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-button type="primary" @click="openUiDialog()">
            <el-icon><Plus /></el-icon>{{ $t("projectCenter.newProject") }}
          </el-button>
        </div>

        <el-table :data="ui.list" v-loading="ui.loading" style="width:100%">
          <el-table-column prop="name" :label="$t('uiAutomation.project.name')" min-width="180" />
          <el-table-column prop="base_url" :label="$t('uiAutomation.project.baseUrl')" min-width="220" show-overflow-tooltip />
          <el-table-column prop="status" :label="$t('uiAutomation.project.status')" width="110">
            <template #default="{ row }">
              <el-tag :type="uiStatusType(row.status)">{{ uiStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="owner.username" :label="$t('uiAutomation.project.owner')" width="120" />
          <el-table-column prop="created_at" :label="$t('uiAutomation.project.createdAt')" width="170">
            <template #default="{ row }">{{ fmt(row.created_at) }}</template>
          </el-table-column>
          <el-table-column :label="$t('uiAutomation.project.actions')" width="140" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openUiDialog(row)">{{ $t('common.edit') }}</el-button>
              <el-button size="small" type="danger" @click="deleteUiProject(row)">{{ $t('common.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-model:current-page="ui.page" :page-size="ui.pageSize" :total="ui.total"
          layout="total, prev, pager, next" class="pagination"
          @current-change="loadUiProjects"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- ===== AI 项目 Dialog ===== -->
    <el-dialog
      v-model="aiDialog.visible"
      :title="aiDialog.editing ? $t('project.editProject') : $t('project.createProject')"
      width="500px" :close-on-click-modal="false" @close="resetAiForm"
    >
      <el-form ref="aiFormRef" :model="aiDialog.form" :rules="aiRules" label-width="90px">
        <el-form-item :label="$t('project.projectName')" prop="name">
          <el-input v-model="aiDialog.form.name" />
        </el-form-item>
        <el-form-item :label="$t('project.projectDescription')">
          <el-input v-model="aiDialog.form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="$t('project.status')" prop="status">
          <el-select v-model="aiDialog.form.status" style="width:100%">
            <el-option :label="$t('project.active')" value="active" />
            <el-option :label="$t('project.paused')" value="paused" />
            <el-option :label="$t('project.completed')" value="completed" />
            <el-option :label="$t('project.archived')" value="archived" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="aiDialog.visible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="aiDialog.submitting" @click="submitAiForm">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- ===== API 项目 Dialog ===== -->
    <el-dialog
      v-model="apiDialog.visible"
      :title="apiDialog.editing ? $t('apiTesting.project.editProject') : $t('apiTesting.project.createProject')"
      width="600px" :close-on-click-modal="false" @close="resetApiForm"
    >
      <el-form ref="apiFormRef" :model="apiDialog.form" :rules="apiRules" label-width="100px">
        <el-form-item :label="$t('apiTesting.project.projectName')" prop="name">
          <el-input v-model="apiDialog.form.name" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.project.projectDescription')">
          <el-input v-model="apiDialog.form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.project.projectType')" prop="project_type">
          <el-radio-group v-model="apiDialog.form.project_type">
            <el-radio value="HTTP">HTTP</el-radio>
            <el-radio value="WEBSOCKET">WebSocket</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.project.projectStatus')" prop="status">
          <el-select v-model="apiDialog.form.status" style="width:100%">
            <el-option :label="$t('apiTesting.project.status.notStarted')" value="NOT_STARTED" />
            <el-option :label="$t('apiTesting.project.status.inProgress')" value="IN_PROGRESS" />
            <el-option :label="$t('apiTesting.project.status.completed')" value="COMPLETED" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.project.owner')" prop="owner">
          <el-select v-model="apiDialog.form.owner" filterable style="width:100%">
            <el-option v-for="u in users" :key="u.id" :label="u.username" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.project.teamMembers')">
          <el-select v-model="apiDialog.form.member_ids" multiple filterable style="width:100%">
            <el-option v-for="u in users" :key="u.id" :label="u.username" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.common.visibility')">
          <el-radio-group v-model="apiDialog.form.visibility">
            <el-radio value="all">{{ $t('apiTesting.common.visibleAll') }}</el-radio>
            <el-radio value="private">{{ $t('apiTesting.common.visibleSelf') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('apiTesting.project.startDate')">
          <el-date-picker v-model="apiDialog.form.start_date" type="date" style="width:100%" />
        </el-form-item>
        <el-form-item :label="$t('apiTesting.project.endDate')">
          <el-date-picker v-model="apiDialog.form.end_date" type="date" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="apiDialog.visible = false">{{ $t('apiTesting.common.cancel') }}</el-button>
        <el-button type="primary" :loading="apiDialog.submitting" @click="submitApiForm">
          {{ apiDialog.editing ? $t('apiTesting.common.update') : $t('apiTesting.common.create') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- API 项目详情 Dialog -->
    <el-dialog v-model="apiDialog.viewVisible" :title="$t('apiTesting.project.viewProject')" width="560px">
      <el-descriptions :column="1" border>
        <el-descriptions-item :label="$t('apiTesting.project.projectName')">{{ apiDialog.viewed?.name }}</el-descriptions-item>
        <el-descriptions-item :label="$t('apiTesting.project.projectDescription')">{{ apiDialog.viewed?.description }}</el-descriptions-item>
        <el-descriptions-item :label="$t('apiTesting.project.projectType')">
          <el-tag :type="apiDialog.viewed?.project_type === 'HTTP' ? 'primary' : 'success'">{{ apiDialog.viewed?.project_type }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('apiTesting.project.projectStatus')">
          <el-tag :type="apiStatusType(apiDialog.viewed?.status)">{{ apiStatusText(apiDialog.viewed?.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('apiTesting.project.owner')">{{ apiDialog.viewed?.owner?.username }}</el-descriptions-item>
        <el-descriptions-item :label="$t('apiTesting.project.teamMembers')">
          <el-tag v-for="m in apiDialog.viewed?.members" :key="m.id" size="small" style="margin:2px">{{ m.username }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="$t('apiTesting.project.startDate')">{{ apiDialog.viewed?.start_date }}</el-descriptions-item>
        <el-descriptions-item :label="$t('apiTesting.project.endDate')">{{ apiDialog.viewed?.end_date }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="apiDialog.viewVisible = false">{{ $t('apiTesting.common.close') }}</el-button>
        <el-button type="primary" @click="openApiDialog(apiDialog.viewed); apiDialog.viewVisible = false">{{ $t('apiTesting.common.edit') }}</el-button>
      </template>
    </el-dialog>

    <!-- ===== UI 项目 Dialog ===== -->
    <el-dialog
      v-model="uiDialog.visible"
      :title="uiDialog.editing ? $t('uiAutomation.project.edit') : $t('uiAutomation.project.create')"
      width="560px" :close-on-click-modal="false" @close="resetUiForm"
    >
      <el-form ref="uiFormRef" :model="uiDialog.form" :rules="uiRules" label-width="100px">
        <el-form-item :label="$t('uiAutomation.project.name')" prop="name">
          <el-input v-model="uiDialog.form.name" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.project.description')">
          <el-input v-model="uiDialog.form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.project.baseUrl')" prop="base_url">
          <el-input v-model="uiDialog.form.base_url" placeholder="https://example.com" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.project.status')" prop="status">
          <el-select v-model="uiDialog.form.status" style="width:100%">
            <el-option :label="$t('uiAutomation.project.statusNotStarted')" value="NOT_STARTED" />
            <el-option :label="$t('uiAutomation.project.statusInProgress')" value="IN_PROGRESS" />
            <el-option :label="$t('uiAutomation.project.statusCompleted')" value="COMPLETED" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.project.owner')" prop="owner">
          <el-select v-model="uiDialog.form.owner" filterable style="width:100%">
            <el-option v-for="u in users" :key="u.id" :label="u.username" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.project.members')">
          <el-select v-model="uiDialog.form.member_ids" multiple filterable style="width:100%">
            <el-option v-for="u in users" :key="u.id" :label="u.username" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.project.startDate')">
          <el-date-picker v-model="uiDialog.form.start_date" type="date" style="width:100%" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.project.endDate')">
          <el-date-picker v-model="uiDialog.form.end_date" type="date" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uiDialog.visible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="uiDialog.submitting" @click="submitUiForm">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Search } from "@element-plus/icons-vue";
import api from "@/utils/api";
import dayjs from "dayjs";

const router = useRouter();
const { t } = useI18n();

const activeTab = ref("ai");
const users = ref([]);

const fmt = (d) => d ? dayjs(d).format("YYYY-MM-DD HH:mm") : "";

// ─── AI 项目 ───────────────────────────────────────────
const ai = reactive({ list: [], loading: false, page: 1, pageSize: 20, total: 0, search: "", statusFilter: "" });
const aiFormRef = ref();
const aiDialog = reactive({ visible: false, editing: null, submitting: false, form: { name: "", description: "", status: "active" } });
const aiRules = computed(() => ({
  name: [{ required: true, message: t("project.projectNameRequired"), trigger: "blur" }],
  status: [{ required: true, message: t("project.projectStatusRequired"), trigger: "change" }],
}));

const loadAiProjects = async () => {
  ai.loading = true;
  try {
    const res = await api.get("/projects/", { params: { page: ai.page, search: ai.search, status: ai.statusFilter } });
    ai.list = res.data.results;
    ai.total = res.data.count;
  } catch { ElMessage.error(t("project.fetchListFailed")); }
  finally { ai.loading = false; }
};

const aiStatusType = (s) => ({ active: "success", paused: "warning", completed: "info", archived: "info" }[s] || "info");
const aiStatusText = (s) => ({ active: t("project.active"), paused: t("project.paused"), completed: t("project.completed"), archived: t("project.archived") }[s] || s);

const openAiDialog = (row = null) => {
  aiDialog.editing = row;
  aiDialog.form = row
    ? { name: row.name, description: row.description, status: row.status }
    : { name: "", description: "", status: "active" };
  aiDialog.visible = true;
};

const resetAiForm = () => { aiDialog.editing = null; aiFormRef.value?.clearValidate(); };

const submitAiForm = async () => {
  if (!await aiFormRef.value?.validate().catch(() => false)) return;
  aiDialog.submitting = true;
  try {
    if (aiDialog.editing) {
      await api.put(`/projects/${aiDialog.editing.id}/`, aiDialog.form);
      ElMessage.success(t("project.updateSuccess"));
    } else {
      await api.post("/projects/", aiDialog.form);
      ElMessage.success(t("project.createSuccess"));
    }
    aiDialog.visible = false;
    loadAiProjects();
  } catch { ElMessage.error(aiDialog.editing ? t("project.updateFailed") : t("project.createFailed")); }
  finally { aiDialog.submitting = false; }
};

const deleteAiProject = async (row) => {
  try {
    await ElMessageBox.confirm(t("project.deleteConfirm"), t("common.warning"), { type: "warning", confirmButtonText: t("common.confirm"), cancelButtonText: t("common.cancel") });
    await api.delete(`/projects/${row.id}/`);
    ElMessage.success(t("project.deleteSuccess"));
    loadAiProjects();
  } catch (e) { if (e !== "cancel") ElMessage.error(t("project.deleteFailed")); }
};

// ─── API 测试项目 ──────────────────────────────────────
const api_ = reactive({ list: [], loading: false, page: 1, pageSize: 20, total: 0 });
// 避免与 import api 冲突，使用别名
const apiState = api_;
const apiFormRef = ref();
const apiDialog = reactive({
  visible: false, editing: null, submitting: false, viewVisible: false, viewed: null,
  form: { name: "", description: "", project_type: "HTTP", status: "NOT_STARTED", owner: null, member_ids: [], visibility: "all", start_date: "", end_date: "" }
});
const apiRules = computed(() => ({
  name: [{ required: true, message: t("apiTesting.project.inputProjectName"), trigger: "blur" }],
  project_type: [{ required: true, trigger: "change" }],
  status: [{ required: true, trigger: "change" }],
  owner: [{ required: true, message: t("apiTesting.project.selectOwner"), trigger: "change" }],
}));

const loadApiProjects = async () => {
  apiState.loading = true;
  try {
    const res = await api.get("/api-testing/projects/", { params: { page: apiState.page, page_size: apiState.pageSize } });
    apiState.list = res.data.results;
    apiState.total = res.data.count;
  } catch { ElMessage.error(t("apiTesting.messages.error.loadProjects")); }
  finally { apiState.loading = false; }
};

const apiStatusType = (s) => ({ NOT_STARTED: "info", IN_PROGRESS: "warning", COMPLETED: "success" }[s] || "info");
const apiStatusText = (s) => ({ NOT_STARTED: t("apiTesting.project.status.notStarted"), IN_PROGRESS: t("apiTesting.project.status.inProgress"), COMPLETED: t("apiTesting.project.status.completed") }[s] || s);

const openApiDialog = (row = null) => {
  apiDialog.editing = row;
  apiDialog.form = row
    ? { name: row.name, description: row.description, project_type: row.project_type, status: row.status, owner: row.owner?.id, member_ids: row.members?.map(m => m.id) || [], visibility: row.visibility ?? "all", start_date: row.start_date || "", end_date: row.end_date || "" }
    : { name: "", description: "", project_type: "HTTP", status: "NOT_STARTED", owner: null, member_ids: [], visibility: "all", start_date: "", end_date: "" };
  apiDialog.visible = true;
};

const viewApiProject = (row) => { apiDialog.viewed = row; apiDialog.viewVisible = true; };
const resetApiForm = () => { apiDialog.editing = null; apiFormRef.value?.resetFields(); };

const submitApiForm = async () => {
  if (!await apiFormRef.value?.validate().catch(() => false)) return;
  apiDialog.submitting = true;
  try {
    const data = { ...apiDialog.form };
    if (data.start_date) data.start_date = dayjs(data.start_date).format("YYYY-MM-DD");
    if (data.end_date) data.end_date = dayjs(data.end_date).format("YYYY-MM-DD");
    if (apiDialog.editing) {
      await api.put(`/api-testing/projects/${apiDialog.editing.id}/`, data);
      ElMessage.success(t("apiTesting.messages.success.projectUpdated"));
    } else {
      await api.post("/api-testing/projects/", data);
      ElMessage.success(t("apiTesting.messages.success.projectCreated"));
    }
    apiDialog.visible = false;
    loadApiProjects();
  } catch { ElMessage.error(apiDialog.editing ? t("apiTesting.messages.error.updateFailed") : t("apiTesting.messages.error.createFailed")); }
  finally { apiDialog.submitting = false; }
};

const deleteApiProject = async (row) => {
  try {
    await ElMessageBox.confirm(t("apiTesting.project.confirmDelete", { name: row.name }), t("apiTesting.messages.confirm.deleteTitle"), { type: "warning", confirmButtonText: t("apiTesting.common.confirm"), cancelButtonText: t("apiTesting.common.cancel") });
    await api.delete(`/api-testing/projects/${row.id}/`);
    ElMessage.success(t("apiTesting.messages.success.delete"));
    loadApiProjects();
  } catch (e) { if (e !== "cancel") ElMessage.error(t("apiTesting.messages.error.deleteFailed")); }
};

// ─── UI 自动化项目 ─────────────────────────────────────
const ui = reactive({ list: [], loading: false, page: 1, pageSize: 20, total: 0, search: "" });
const uiFormRef = ref();
const uiDialog = reactive({
  visible: false, editing: null, submitting: false,
  form: { name: "", description: "", base_url: "", status: "IN_PROGRESS", owner: null, member_ids: [], start_date: "", end_date: "" }
});
const uiRules = computed(() => ({
  name: [{ required: true, message: t("uiAutomation.project.nameRequired"), trigger: "blur" }],
  base_url: [{ required: true, message: t("uiAutomation.project.baseUrlRequired"), trigger: "blur" }],
  status: [{ required: true, trigger: "change" }],
  owner: [{ required: true, message: t("uiAutomation.project.ownerRequired"), trigger: "change" }],
}));

const loadUiProjects = async () => {
  ui.loading = true;
  try {
    const res = await api.get("/ui-automation/projects/", { params: { page: ui.page, page_size: ui.pageSize, search: ui.search } });
    ui.list = res.data.results || res.data;
    ui.total = res.data.count || ui.list.length;
  } catch { ElMessage.error(t("uiAutomation.project.loadFailed")); }
  finally { ui.loading = false; }
};

const uiStatusType = (s) => ({ NOT_STARTED: "info", IN_PROGRESS: "warning", COMPLETED: "success" }[s] || "info");
const uiStatusText = (s) => ({ NOT_STARTED: t("uiAutomation.project.statusNotStarted"), IN_PROGRESS: t("uiAutomation.project.statusInProgress"), COMPLETED: t("uiAutomation.project.statusCompleted") }[s] || s);

const openUiDialog = (row = null) => {
  uiDialog.editing = row;
  uiDialog.form = row
    ? { name: row.name, description: row.description, base_url: row.base_url, status: row.status, owner: row.owner?.id, member_ids: row.members?.map(m => m.id) || [], start_date: row.start_date || "", end_date: row.end_date || "" }
    : { name: "", description: "", base_url: "", status: "IN_PROGRESS", owner: null, member_ids: [], start_date: "", end_date: "" };
  uiDialog.visible = true;
};

const resetUiForm = () => { uiDialog.editing = null; uiFormRef.value?.resetFields(); };

const submitUiForm = async () => {
  if (!await uiFormRef.value?.validate().catch(() => false)) return;
  uiDialog.submitting = true;
  try {
    const data = { ...uiDialog.form };
    if (data.start_date) data.start_date = dayjs(data.start_date).format("YYYY-MM-DD");
    if (data.end_date) data.end_date = dayjs(data.end_date).format("YYYY-MM-DD");
    if (uiDialog.editing) {
      await api.put(`/ui-automation/projects/${uiDialog.editing.id}/`, data);
      ElMessage.success(t("uiAutomation.project.updateSuccess"));
    } else {
      await api.post("/ui-automation/projects/", data);
      ElMessage.success(t("uiAutomation.project.createSuccess"));
    }
    uiDialog.visible = false;
    loadUiProjects();
  } catch { ElMessage.error(uiDialog.editing ? t("uiAutomation.project.updateFailed") : t("uiAutomation.project.createFailed")); }
  finally { uiDialog.submitting = false; }
};

const deleteUiProject = async (row) => {
  try {
    await ElMessageBox.confirm(t("uiAutomation.project.deleteConfirm", { name: row.name }), t("common.warning"), { type: "warning", confirmButtonText: t("common.confirm"), cancelButtonText: t("common.cancel") });
    await api.delete(`/ui-automation/projects/${row.id}/`);
    ElMessage.success(t("uiAutomation.project.deleteSuccess"));
    loadUiProjects();
  } catch (e) { if (e !== "cancel") ElMessage.error(t("uiAutomation.project.deleteFailed")); }
};

// ─── 公共 ──────────────────────────────────────────────
const loadUsers = async () => {
  try {
    const res = await api.get("/api-testing/users/");
    users.value = res.data.results || res.data;
  } catch { users.value = []; }
};

onMounted(() => {
  loadAiProjects();
  loadApiProjects();
  loadUiProjects();
  loadUsers();
});
</script>

<style scoped>
.project-center { padding: 24px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { margin: 0 0 4px; font-size: 20px; color: #303133; }
.page-header p { margin: 0; color: #909399; font-size: 13px; }
.project-tabs { background: #fff; padding: 0 16px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.tab-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; padding-top: 4px; }
.tab-toolbar .el-button { margin-left: auto; }
.pagination { margin-top: 16px; display: flex; justify-content: center; }
</style>
