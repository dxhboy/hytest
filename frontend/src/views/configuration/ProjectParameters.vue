<template>
  <div class="project-parameters-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <el-icon class="title-icon"><Key /></el-icon>
        <div>
          <h2 class="page-title">
            {{ $t("configuration.parameters.title") }}
          </h2>
          <p class="page-desc">
            {{ $t("configuration.parameters.description") }}
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
          @change="fetchParameters"
        >
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="project.name"
            :value="project.id"
          />
        </el-select>
        <el-button
          type="primary"
          :disabled="!projectId"
          @click="openDialog()"
        >
          <el-icon><Plus /></el-icon
          >{{ $t("configuration.parameters.addParameter") }}
        </el-button>
      </div>

      <el-table
        :data="parameters"
        v-loading="loading"
        border
        style="width: 100%"
      >
        <el-table-column
          prop="name"
          :label="$t('configuration.parameters.name')"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column
          prop="value"
          :label="$t('configuration.parameters.value')"
          min-width="220"
          show-overflow-tooltip
        />
        <el-table-column
          prop="description"
          :label="$t('configuration.parameters.description_')"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column
          :label="$t('configuration.parameters.reference')"
          width="200"
        >
          <template #default="{ row }">
            <el-tag
              class="reference-tag"
              @click="copyReference(row)"
            >
              {{ referenceOf(row) }}
              <el-icon class="copy-icon"><CopyDocument /></el-icon>
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_by_name"
          :label="$t('configuration.parameters.createdBy')"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column
          :label="$t('configuration.parameters.actions')"
          width="140"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <div class="action-col">
              <el-button link type="primary" size="small" @click="openDialog(row)">
                {{ $t("uiAutomation.common.edit") }}
              </el-button>
              <span class="action-divider" />
              <el-button link type="danger" size="small" @click="handleDelete(row)">
                {{ $t("uiAutomation.common.delete") }}
              </el-button>
            </div>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty
            :description="
              projectId
                ? $t('configuration.parameters.emptyDescription')
                : $t('uiAutomation.common.selectProject')
            "
          />
        </template>
      </el-table>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="520px"
      :close-on-click-modal="false"
      @close="resetForm"
    >
      <el-form
        :model="form"
        :rules="formRules"
        ref="formRef"
        label-width="100px"
      >
        <el-form-item
          :label="$t('configuration.parameters.name')"
          prop="name"
        >
          <el-input
            v-model="form.name"
            :placeholder="$t('configuration.parameters.namePlaceholder')"
            clearable
          />
        </el-form-item>

        <el-form-item
          :label="$t('configuration.parameters.value')"
          prop="value"
        >
          <el-input
            v-model="form.value"
            :placeholder="$t('configuration.parameters.valuePlaceholder')"
            clearable
          />
        </el-form-item>

        <el-form-item :label="$t('configuration.parameters.description_')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="2"
            :placeholder="
              $t('configuration.parameters.descriptionPlaceholder')
            "
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
import { Key, Plus, CopyDocument } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import {
  getUiProjects,
  getUiProjectParameters,
  createUiProjectParameter,
  updateUiProjectParameter,
  deleteUiProjectParameter,
} from "@/api/ui_automation";

const { t } = useI18n();
const route = useRoute();

const projects = ref([]);
const projectId = ref("");
const parameters = ref([]);
const loading = ref(false);

const dialogVisible = ref(false);
const isEdit = ref(false);
const editId = ref(null);
const submitting = ref(false);
const formRef = ref(null);

const NAME_PATTERN = /^[a-zA-Z_][a-zA-Z0-9_]*$/;

const defaultForm = () => ({
  name: "",
  value: "",
  description: "",
});

const form = reactive(defaultForm());

const formRules = computed(() => ({
  name: [
    {
      required: true,
      message: t("configuration.parameters.rules.nameRequired"),
      trigger: "blur",
    },
    {
      pattern: NAME_PATTERN,
      message: t("configuration.parameters.rules.namePattern"),
      trigger: "blur",
    },
  ],
  value: [
    {
      required: true,
      message: t("configuration.parameters.rules.valueRequired"),
      trigger: "blur",
    },
  ],
}));

const dialogTitle = computed(() =>
  isEdit.value
    ? t("configuration.parameters.editParameter")
    : t("configuration.parameters.addParameter"),
);

const referenceOf = (row) => `{{${row.name}}}`;

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

const fetchParameters = async () => {
  if (!projectId.value) {
    parameters.value = [];
    return;
  }
  loading.value = true;
  try {
    const res = await getUiProjectParameters({
      project: projectId.value,
      page_size: 500,
    });
    parameters.value = res.data.results || res.data || [];
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
    form.name = row.name;
    form.value = row.value;
    form.description = row.description || "";
  } else {
    Object.assign(form, defaultForm());
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

  const payload = {
    project: projectId.value,
    name: form.name,
    value: form.value,
    description: form.description,
  };

  submitting.value = true;
  try {
    if (isEdit.value) {
      await updateUiProjectParameter(editId.value, payload);
      ElMessage.success(t("uiAutomation.messages.success.update"));
    } else {
      await createUiProjectParameter(payload);
      ElMessage.success(t("uiAutomation.messages.success.create"));
    }
    dialogVisible.value = false;
    await fetchParameters();
  } catch (err) {
    const detail = err.response?.data;
    const isDuplicate =
      err.response?.status === 400 &&
      JSON.stringify(detail || "").includes("unique");
    ElMessage.error(
      isDuplicate
        ? t("configuration.parameters.messages.duplicateName")
        : detail?.detail || t("uiAutomation.messages.error.save"),
    );
  } finally {
    submitting.value = false;
  }
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      t("configuration.parameters.confirmDelete"),
      t("configuration.common.delete"),
      {
        type: "warning",
        confirmButtonText: t("configuration.common.confirm"),
        cancelButtonText: t("configuration.common.cancel"),
        confirmButtonClass: "el-button--danger",
      },
    );
    await deleteUiProjectParameter(row.id);
    ElMessage.success(t("uiAutomation.messages.success.delete"));
    await fetchParameters();
  } catch (err) {
    if (err !== "cancel")
      ElMessage.error(t("uiAutomation.messages.error.delete"));
  }
};

const copyReference = async (row) => {
  const referenceText = referenceOf(row);
  try {
    await navigator.clipboard.writeText(referenceText);
    ElMessage.success(
      t("configuration.parameters.copyReferenceSuccess", {
        ref: referenceText,
      }),
    );
  } catch {
    ElMessage.error(referenceText);
  }
};

onMounted(async () => {
  await fetchProjects();
  await fetchParameters();
});
</script>

<style scoped>
.project-parameters-page {
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

.reference-tag {
  cursor: pointer;
  font-family: "Courier New", monospace;
}

.copy-icon {
  margin-left: 4px;
  font-size: 12px;
}
</style>
