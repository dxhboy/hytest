<template>
  <div class="remote-browser-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <el-icon class="title-icon"><Monitor /></el-icon>
        <div>
          <h2 class="page-title">
            {{ $t("configuration.remoteBrowser.title") }}
          </h2>
          <p class="page-desc">
            {{ $t("configuration.remoteBrowser.description") }}
          </p>
        </div>
      </div>
    </div>

    <!-- 主卡片 -->
    <div class="main-card">
      <div class="section-toolbar">
        <el-select
          v-model="projectId"
          :placeholder="$t('uiAutomation.common.selectProject')"
          style="width: 220px; margin-right: 12px"
          @change="fetchServices"
        >
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
        <el-button type="primary" @click="openDialog()">
          <el-icon><Plus /></el-icon
          >{{ $t("configuration.remoteBrowser.addService") }}
        </el-button>
      </div>

      <el-table :data="services" v-loading="loading" border style="width: 100%">
        <el-table-column
          prop="name"
          :label="$t('configuration.remoteBrowser.name')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column
          prop="service_type_display"
          :label="$t('configuration.remoteBrowser.serviceType')"
          width="160"
        />
        <el-table-column
          prop="url"
          :label="$t('configuration.remoteBrowser.url')"
          min-width="260"
          show-overflow-tooltip
        />
        <el-table-column
          :label="$t('configuration.remoteBrowser.isActive')"
          width="90"
          align="center"
        >
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              @change="toggleActive(row)"
            />
          </template>
        </el-table-column>
        <el-table-column
          prop="created_by_name"
          :label="$t('configuration.remoteBrowser.createdBy')"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column
          :label="$t('configuration.remoteBrowser.actions')"
          width="200"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button
              text
              type="primary"
              size="small"
              :loading="row.testing"
              @click="handleTestConnection(row)"
            >
              {{ $t("configuration.remoteBrowser.testConnection") }}
            </el-button>
            <el-button
              text
              type="primary"
              size="small"
              @click="openDialog(row)"
            >
              {{ $t("uiAutomation.common.edit") }}
            </el-button>
            <el-button
              text
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >
              {{ $t("uiAutomation.common.delete") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="600px"
      :close-on-click-modal="false"
      @close="resetForm"
    >
      <el-form
        :model="form"
        :rules="formRules"
        ref="formRef"
        label-width="130px"
      >
        <el-form-item
          :label="$t('configuration.remoteBrowser.name')"
          prop="name"
        >
          <el-input v-model="form.name" clearable />
        </el-form-item>

        <el-form-item
          :label="$t('configuration.remoteBrowser.serviceType')"
          prop="service_type"
        >
          <el-select v-model="form.service_type" style="width: 100%">
            <el-option label="Selenium Grid" value="selenium_grid" />
            <el-option label="Playwright Remote" value="playwright_remote" />
            <el-option label="Playwright CDP" value="playwright_cdp" />
            <el-option label="BrowserStack" value="browserstack" />
            <el-option label="Sauce Labs" value="saucelabs" />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('configuration.remoteBrowser.url')" prop="url">
          <el-input
            v-model="form.url"
            :placeholder="urlPlaceholder"
            clearable
          />
        </el-form-item>

        <template v-if="isCloudService">
          <el-divider>{{
            $t("configuration.remoteBrowser.authConfig")
          }}</el-divider>
          <el-form-item :label="$t('configuration.remoteBrowser.username')">
            <el-input v-model="form.auth_config.username" clearable />
          </el-form-item>
          <el-form-item :label="$t('configuration.remoteBrowser.accessKey')">
            <el-input
              v-model="form.auth_config.access_key"
              type="password"
              show-password
              clearable
            />
          </el-form-item>
        </template>

        <el-divider />
        <el-collapse>
          <el-collapse-item
            :title="$t('configuration.remoteBrowser.capabilities')"
            name="capabilities"
          >
            <el-input
              v-model="capabilitiesJson"
              type="textarea"
              :rows="6"
              placeholder="{}"
            />
          </el-collapse-item>
        </el-collapse>

        <el-form-item
          :label="$t('configuration.remoteBrowser.isActive')"
          style="margin-top: 18px"
        >
          <el-switch
            v-model="form.is_active"
            :active-text="$t('configuration.common.enabled')"
            :inactive-text="$t('configuration.common.disabled')"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{
          $t("configuration.common.cancel")
        }}</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ $t("configuration.common.confirm") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Monitor, Plus } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import {
  getUiProjects,
  getRemoteBrowserServices,
  createRemoteBrowserService,
  updateRemoteBrowserService,
  deleteRemoteBrowserService,
  testRemoteBrowserConnection,
} from "@/api/ui_automation";

const { t } = useI18n();
const route = useRoute();

const projects = ref([]);
const projectId = ref("");
const services = ref([]);
const loading = ref(false);

const dialogVisible = ref(false);
const isEdit = ref(false);
const editId = ref(null);
const submitting = ref(false);
const formRef = ref(null);
const capabilitiesRaw = ref("{}");

const defaultForm = () => ({
  project: null,
  name: "",
  service_type: "selenium_grid",
  url: "",
  capabilities: {},
  auth_config: { username: "", access_key: "" },
  is_active: true,
});

const form = reactive(defaultForm());

const formRules = computed(() => ({
  name: [
    {
      required: true,
      message: t("configuration.remoteBrowser.rules.nameRequired"),
      trigger: "blur",
    },
  ],
  url: [
    {
      required: true,
      message: t("configuration.remoteBrowser.rules.urlRequired"),
      trigger: "blur",
    },
  ],
}));

const CLOUD_SERVICE_TYPES = ["browserstack", "saucelabs"];

const isCloudService = computed(() =>
  CLOUD_SERVICE_TYPES.includes(form.service_type),
);

const urlPlaceholder = computed(() =>
  t(`configuration.remoteBrowser.placeholders.${form.service_type}`),
);

const dialogTitle = computed(() =>
  isEdit.value
    ? t("configuration.remoteBrowser.editService")
    : t("configuration.remoteBrowser.addService"),
);

// capabilities JSON 字符串 <-> 文本框内容
const capabilitiesJson = computed({
  get: () => capabilitiesRaw.value,
  set: (val) => {
    capabilitiesRaw.value = val;
  },
});

const fetchProjects = async () => {
  try {
    const res = await getUiProjects({ page_size: 100 });
    projects.value = res.data.results || res.data || [];
    const queryProject = route.query.project;
    if (
      queryProject &&
      projects.value.some((p) => String(p.id) === String(queryProject))
    ) {
      projectId.value = queryProject;
    } else if (projects.value.length > 0) {
      projectId.value = projects.value[0].id;
    }
  } catch {
    ElMessage.error(t("uiAutomation.messages.error.load"));
  }
};

const fetchServices = async () => {
  if (!projectId.value) {
    services.value = [];
    return;
  }
  loading.value = true;
  try {
    const res = await getRemoteBrowserServices({
      project: projectId.value,
      page_size: 500,
    });
    services.value = res.data.results || res.data || [];
  } catch {
    ElMessage.error(t("uiAutomation.messages.error.load"));
  } finally {
    loading.value = false;
  }
};

const openDialog = (row = null) => {
  isEdit.value = !!row;
  editId.value = row?.id || null;
  if (row) {
    form.project = row.project;
    form.name = row.name;
    form.service_type = row.service_type;
    form.url = row.url;
    form.is_active = row.is_active;
    form.auth_config = {
      username: "",
      access_key: "",
      ...(row.auth_config || {}),
    };
    capabilitiesRaw.value = JSON.stringify(row.capabilities || {}, null, 2);
  } else {
    Object.assign(form, defaultForm());
    form.project = projectId.value;
    capabilitiesRaw.value = "{}";
  }
  dialogVisible.value = true;
};

const resetForm = () => {
  formRef.value?.resetFields();
  editId.value = null;
};

const handleSubmit = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  let capabilities = {};
  try {
    capabilities = capabilitiesRaw.value
      ? JSON.parse(capabilitiesRaw.value)
      : {};
  } catch {
    ElMessage.error(
      t("configuration.remoteBrowser.messages.invalidCapabilities"),
    );
    return;
  }

  const payload = {
    project: form.project || projectId.value,
    name: form.name,
    service_type: form.service_type,
    url: form.url,
    capabilities,
    auth_config: isCloudService.value ? { ...form.auth_config } : {},
    is_active: form.is_active,
  };

  submitting.value = true;
  try {
    if (isEdit.value) {
      await updateRemoteBrowserService(editId.value, payload);
      ElMessage.success(t("uiAutomation.messages.success.update"));
    } else {
      await createRemoteBrowserService(payload);
      ElMessage.success(t("uiAutomation.messages.success.create"));
    }
    dialogVisible.value = false;
    await fetchServices();
  } catch (err) {
    ElMessage.error(
      err.response?.data?.detail || t("uiAutomation.messages.error.save"),
    );
  } finally {
    submitting.value = false;
  }
};

const toggleActive = async (row) => {
  const nextActive = !row.is_active;
  try {
    await updateRemoteBrowserService(row.id, {
      project: row.project,
      name: row.name,
      service_type: row.service_type,
      url: row.url,
      capabilities: row.capabilities || {},
      auth_config: row.auth_config || {},
      is_active: nextActive,
    });
    row.is_active = nextActive;
    ElMessage.success(
      nextActive
        ? t("configuration.common.enabled")
        : t("configuration.common.disabled"),
    );
  } catch {
    ElMessage.error(t("uiAutomation.messages.error.update"));
  }
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      t("configuration.remoteBrowser.confirmDelete"),
      t("configuration.common.delete"),
      {
        type: "warning",
        confirmButtonText: t("configuration.common.confirm"),
        cancelButtonText: t("configuration.common.cancel"),
        confirmButtonClass: "el-button--danger",
      },
    );
    await deleteRemoteBrowserService(row.id);
    ElMessage.success(t("uiAutomation.messages.success.delete"));
    await fetchServices();
  } catch (err) {
    if (err !== "cancel")
      ElMessage.error(t("uiAutomation.messages.error.delete"));
  }
};

const handleTestConnection = async (row) => {
  row.testing = true;
  try {
    const res = await testRemoteBrowserConnection(row.id);
    ElMessage.success(
      res.data?.message || t("configuration.remoteBrowser.testSuccess"),
    );
  } catch (err) {
    ElMessage.error(
      err.response?.data?.message ||
        err.response?.data?.detail ||
        t("configuration.remoteBrowser.testFailed"),
    );
  } finally {
    row.testing = false;
  }
};

onMounted(async () => {
  await fetchProjects();
  await fetchServices();
});
</script>

<style scoped>
.remote-browser-page {
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: center;
  margin-bottom: 24px;
  padding: 20px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 10px;
  color: white;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.title-icon {
  font-size: 32px;
  flex-shrink: 0;
}

.page-title {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 600;
}

.page-desc {
  margin: 0;
  font-size: 13px;
  opacity: 0.85;
}

.main-card {
  background: white;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 16px 16px 16px;
}

.section-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 14px;
}
</style>
