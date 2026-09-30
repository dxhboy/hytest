<template>
  <div class="notification-config-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <el-icon class="title-icon"><Bell /></el-icon>
        <div>
          <h2 class="page-title">{{ $t("configuration.notification.title") }}</h2>
          <p class="page-desc">{{ $t("configuration.notification.description") }}</p>
        </div>
      </div>
    </div>

    <!-- 主 Tab -->
    <div class="main-card">
      <el-tabs v-model="mainTab">
        <!-- Tab 1: 机器人通知 -->
        <el-tab-pane :label="$t('configuration.notification.tabs.bot')" name="bot">
          <el-tabs v-model="botTab" type="card" class="bot-tabs">
            <!-- 飞书 -->
            <el-tab-pane name="webhook_feishu" :label="$t('configuration.notification.tabs.feishu')">
              <div class="section-toolbar">
                <el-button type="primary" @click="openDialog('webhook_feishu')">
                  <el-icon><Plus /></el-icon>{{ $t("configuration.notification.add.feishu") }}
                </el-button>
              </div>
              <el-table :data="botsByType('webhook_feishu')" v-loading="loading" border style="width:100%">
                <el-table-column prop="name" :label="$t('configuration.notification.columns.configName')" min-width="140" show-overflow-tooltip />
                <el-table-column label="Webhook URL" min-width="260" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="url-text">{{ row.webhook_bots?.webhook_url || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.secret')" width="90" align="center">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.webhook_bots?.secret ? 'success' : 'info'">
                      {{ row.webhook_bots?.secret ? $t('configuration.notification.secretConfigured') : $t('configuration.notification.secretNotConfigured') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.scope')" width="160" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.webhook_bots?.enable_api_testing" size="small" style="margin-right:4px">{{ $t("configuration.notification.scope.apiTesting") }}</el-tag>
                    <el-tag v-if="row.webhook_bots?.enable_ui_automation" size="small" type="warning">{{ $t("configuration.notification.scope.uiAutomation") }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.status')" width="80" align="center">
                  <template #default="{ row }">
                    <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.visibility')" width="120" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.visibility === 'all' ? 'success' : 'warning'" size="small">
                      {{ row.visibility === 'all' ? $t('configuration.notification.visibleAll') : $t('configuration.notification.visibleSelf') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.creator')" width="100" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.created_by_name }}</template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.operation')" width="140" align="center" fixed="right">
                  <template #default="{ row }">
                    <div class="action-col">
                      <el-button link type="primary" size="small" @click="openDialog('webhook_feishu', row)">{{ $t("common.edit") }}</el-button>
                      <span class="action-divider" />
                      <el-button link type="danger" size="small" @click="deleteConfig(row)">{{ $t("common.delete") }}</el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 企业微信 -->
            <el-tab-pane name="webhook_wechat" :label="$t('configuration.notification.types.webhook_wechat')">
              <div class="section-toolbar">
                <el-button type="primary" @click="openDialog('webhook_wechat')">
                  <el-icon><Plus /></el-icon>{{ $t("configuration.notification.add.wechat") }}
                </el-button>
              </div>
              <el-table :data="botsByType('webhook_wechat')" v-loading="loading" border style="width:100%">
                <el-table-column prop="name" :label="$t('configuration.notification.columns.configName')" min-width="140" show-overflow-tooltip />
                <el-table-column label="Webhook URL" min-width="280" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="url-text">{{ row.webhook_bots?.webhook_url || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.scope')" width="160" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.webhook_bots?.enable_api_testing" size="small" style="margin-right:4px">{{ $t("configuration.notification.scope.apiTesting") }}</el-tag>
                    <el-tag v-if="row.webhook_bots?.enable_ui_automation" size="small" type="warning">{{ $t("configuration.notification.scope.uiAutomation") }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.status')" width="80" align="center">
                  <template #default="{ row }">
                    <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.visibility')" width="120" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.visibility === 'all' ? 'success' : 'warning'" size="small">
                      {{ row.visibility === 'all' ? $t('configuration.notification.visibleAll') : $t('configuration.notification.visibleSelf') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.creator')" width="100" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.created_by_name }}</template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.operation')" width="140" align="center" fixed="right">
                  <template #default="{ row }">
                    <div class="action-col">
                      <el-button link type="primary" size="small" @click="openDialog('webhook_wechat', row)">{{ $t("common.edit") }}</el-button>
                      <span class="action-divider" />
                      <el-button link type="danger" size="small" @click="deleteConfig(row)">{{ $t("common.delete") }}</el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 钉钉 -->
            <el-tab-pane name="webhook_dingtalk" :label="$t('configuration.notification.types.webhook_dingtalk')">
              <div class="section-toolbar">
                <el-button type="primary" @click="openDialog('webhook_dingtalk')">
                  <el-icon><Plus /></el-icon>{{ $t("configuration.notification.add.dingtalk") }}
                </el-button>
              </div>
              <el-table :data="botsByType('webhook_dingtalk')" v-loading="loading" border style="width:100%">
                <el-table-column prop="name" :label="$t('configuration.notification.columns.configName')" min-width="140" show-overflow-tooltip />
                <el-table-column label="Webhook URL" min-width="260" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="url-text">{{ row.webhook_bots?.webhook_url || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.secret')" width="90" align="center">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.webhook_bots?.secret ? 'success' : 'info'">
                      {{ row.webhook_bots?.secret ? $t('configuration.notification.secretConfigured') : $t('configuration.notification.secretNotConfigured') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.scope')" width="160" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.webhook_bots?.enable_api_testing" size="small" style="margin-right:4px">{{ $t("configuration.notification.scope.apiTesting") }}</el-tag>
                    <el-tag v-if="row.webhook_bots?.enable_ui_automation" size="small" type="warning">{{ $t("configuration.notification.scope.uiAutomation") }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.status')" width="80" align="center">
                  <template #default="{ row }">
                    <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.visibility')" width="120" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.visibility === 'all' ? 'success' : 'warning'" size="small">
                      {{ row.visibility === 'all' ? $t('configuration.notification.visibleAll') : $t('configuration.notification.visibleSelf') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.creator')" width="100" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.created_by_name }}</template>
                </el-table-column>
                <el-table-column :label="$t('configuration.notification.columns.operation')" width="140" align="center" fixed="right">
                  <template #default="{ row }">
                    <div class="action-col">
                      <el-button link type="primary" size="small" @click="openDialog('webhook_dingtalk', row)">{{ $t("common.edit") }}</el-button>
                      <span class="action-divider" />
                      <el-button link type="danger" size="small" @click="deleteConfig(row)">{{ $t("common.delete") }}</el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>

        <!-- Tab 2: 邮件配置 -->
        <el-tab-pane :label="$t('configuration.notification.types.email')" name="email">
          <div class="section-toolbar">
            <el-button type="primary" @click="openDialog('email')">
              <el-icon><Plus /></el-icon>{{ $t("configuration.notification.add.email") }}
            </el-button>
          </div>
          <el-table :data="botsByType('email')" v-loading="loading" border style="width:100%">
            <el-table-column prop="name" :label="$t('configuration.notification.columns.configName')" min-width="140" show-overflow-tooltip />
            <el-table-column :label="$t('configuration.notification.columns.smtpServer')" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.webhook_bots?.host || '-' }}{{ row.webhook_bots?.port ? ':' + row.webhook_bots.port : '' }}
              </template>
            </el-table-column>
            <el-table-column :label="$t('configuration.notification.columns.senderAccount')" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.webhook_bots?.username || '-' }}</template>
            </el-table-column>
            <el-table-column label="TLS" width="70" align="center">
              <template #default="{ row }">
                <el-tag :type="row.webhook_bots?.use_tls ? 'success' : 'info'" size="small">
                  {{ row.webhook_bots?.use_tls ? $t('configuration.notification.yes') : $t('configuration.notification.no') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('configuration.notification.columns.status')" width="80" align="center">
              <template #default="{ row }">
                <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
              </template>
            </el-table-column>
            <el-table-column :label="$t('configuration.notification.columns.visibility')" width="120" align="center">
              <template #default="{ row }">
                <el-tag :type="row.visibility === 'all' ? 'success' : 'warning'" size="small">
                  {{ row.visibility === 'all' ? $t('configuration.notification.visibleAll') : $t('configuration.notification.visibleSelf') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="$t('configuration.notification.columns.creator')" width="100" show-overflow-tooltip>
              <template #default="{ row }">{{ row.created_by_name }}</template>
            </el-table-column>
            <el-table-column :label="$t('configuration.notification.columns.operation')" width="140" align="center" fixed="right">
              <template #default="{ row }">
                <div class="action-col">
                  <el-button link type="primary" size="small" @click="openDialog('email', row)">{{ $t("common.edit") }}</el-button>
                  <span class="action-divider" />
                  <el-button link type="danger" size="small" @click="deleteConfig(row)">{{ $t("common.delete") }}</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="560px"
      :close-on-click-modal="false"
      @close="resetForm"
    >
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="110px">
        <el-form-item :label="$t('configuration.notification.columns.configName')" prop="name">
          <el-input v-model="form.name" :placeholder="$t('configuration.notification.form.configNamePlaceholder')" clearable />
        </el-form-item>

        <!-- 机器人字段 -->
        <template v-if="form.config_type !== 'email'">
          <el-form-item label="Webhook URL" prop="botData.webhook_url">
            <el-input
              v-model="form.botData.webhook_url"
              :placeholder="webhookPlaceholder"
              clearable
            />
          </el-form-item>
          <el-form-item v-if="form.config_type !== 'webhook_wechat'" :label="$t('configuration.notification.columns.secret')">
            <el-input
              v-model="form.botData.secret"
              :placeholder="$t('configuration.notification.form.secretPlaceholder')"
              type="password"
              show-password
              clearable
            />
          </el-form-item>
          <el-form-item :label="$t('configuration.notification.columns.scope')">
            <el-checkbox v-model="form.botData.enable_api_testing">{{ $t("configuration.notification.form.notifyApiTesting") }}</el-checkbox>
            <el-checkbox v-model="form.botData.enable_ui_automation">{{ $t("configuration.notification.form.notifyUiAutomation") }}</el-checkbox>
          </el-form-item>
        </template>

        <!-- 邮件字段 -->
        <template v-else>
          <el-form-item :label="$t('configuration.notification.columns.smtpServer')" prop="smtp_host">
            <el-input v-model="form.botData.host" :placeholder="$t('configuration.notification.form.smtpHostPlaceholder')" clearable />
          </el-form-item>
          <el-form-item :label="$t('configuration.notification.form.smtpPort')" prop="smtp_port">
            <el-input-number v-model="form.botData.port" :min="1" :max="65535" style="width:100%" />
          </el-form-item>
          <el-form-item :label="$t('configuration.notification.form.username')" prop="smtp_username">
            <el-input v-model="form.botData.username" :placeholder="$t('configuration.notification.form.usernamePlaceholder')" clearable />
          </el-form-item>
          <el-form-item :label="$t('configuration.notification.form.password')">
            <el-input
              v-model="form.botData.password"
              :placeholder="$t('configuration.notification.form.passwordPlaceholder')"
              type="password"
              show-password
              clearable
            />
          </el-form-item>
          <el-form-item :label="$t('configuration.notification.form.fromEmail')">
            <el-input
              v-model="form.botData.from_email"
              :placeholder="$t('configuration.notification.form.fromEmailPlaceholder')"
              clearable
            />
          </el-form-item>
          <el-form-item :label="$t('configuration.notification.form.useTls')">
            <el-switch v-model="form.botData.use_tls" />
          </el-form-item>
        </template>

        <!-- 公共字段 -->
        <el-divider />
        <el-form-item :label="$t('configuration.notification.form.activeStatus')">
          <el-switch v-model="form.is_active" :active-text="$t('configuration.notification.form.enable')" :inactive-text="$t('configuration.notification.form.disable')" />
        </el-form-item>
        <el-form-item :label="$t('configuration.notification.form.visibleScope')">
          <el-radio-group v-model="form.visibility">
            <el-radio value="all">{{ $t("configuration.notification.form.visibleAllUsable") }}</el-radio>
            <el-radio value="private">{{ $t("configuration.notification.form.visibleSelfUsable") }}</el-radio>
          </el-radio-group>
          <div class="form-hint">{{ $t("configuration.notification.form.privateHint") }}</div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t("common.cancel") }}</el-button>
        <el-button type="primary" @click="saveConfig" :loading="saving">{{ $t("common.save") }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Bell, Plus } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import {
  getUnifiedNotificationConfigs,
  createUnifiedNotificationConfig,
  updateUnifiedNotificationConfig,
  deleteUnifiedNotificationConfig,
} from "@/api/core.js";

const { t } = useI18n();

const mainTab = ref("bot");
const botTab = ref("webhook_feishu");
const loading = ref(false);
const saving = ref(false);
const configs = ref([]);

const dialogVisible = ref(false);
const editingId = ref(null);
const formRef = ref(null);

const defaultBotData = () => ({
  webhook_url: "",
  secret: "",
  enabled: true,
  enable_api_testing: true,
  enable_ui_automation: true,
});

const defaultEmailData = () => ({
  host: "",
  port: 465,
  username: "",
  password: "",
  from_email: "",
  use_tls: true,
});

const form = ref({
  config_type: "webhook_feishu",
  name: "",
  botData: defaultBotData(),
  is_active: true,
  visibility: "all",
});

const formRules = computed(() => {
  const rules = {
    name: [{ required: true, message: t("configuration.notification.form.configNamePlaceholder"), trigger: "blur" }],
  };
  if (form.value.config_type !== "email") {
    rules["botData.webhook_url"] = [{ required: true, message: t("configuration.notification.rules.webhookRequired"), trigger: "blur" }];
  } else {
    rules.smtp_host = [{ required: true, message: t("configuration.notification.rules.smtpHostRequired"), trigger: "blur" }];
    rules.smtp_port = [{ required: true, message: t("configuration.notification.rules.smtpPortRequired"), trigger: "blur" }];
    rules.smtp_username = [{ required: true, message: t("configuration.notification.rules.usernameRequired"), trigger: "blur" }];
  }
  return rules;
});

const CONFIG_TYPES = ["webhook_feishu", "webhook_wechat", "webhook_dingtalk", "email"];

const WEBHOOK_PLACEHOLDER = {
  webhook_feishu: "https://open.feishu.cn/open-apis/bot/v2/hook/...",
  webhook_wechat: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...",
  webhook_dingtalk: "https://oapi.dingtalk.com/robot/send?access_token=...",
};

const dialogTitle = computed(() => {
  const type = form.value.config_type;
  const typeName = CONFIG_TYPES.includes(type)
    ? t(`configuration.notification.types.${type}`)
    : "";
  return editingId.value
    ? t("configuration.notification.dialog.editTitle", { type: typeName })
    : t("configuration.notification.dialog.createTitle", { type: typeName });
});

const webhookPlaceholder = computed(
  () => WEBHOOK_PLACEHOLDER[form.value.config_type] || "Webhook URL"
);

const botsByType = (type) => configs.value.filter((c) => c.config_type === type);

const loadConfigs = async () => {
  loading.value = true;
  try {
    const res = await getUnifiedNotificationConfigs({ page_size: 500 });
    configs.value = res.data.results || res.data || [];
  } catch {
    ElMessage.error(t("configuration.notification.messages.loadFailed"));
  } finally {
    loading.value = false;
  }
};

const openDialog = (type, row = null) => {
  editingId.value = row?.id || null;
  form.value.config_type = type;
  if (row) {
    form.value.name = row.name;
    form.value.is_active = row.is_active;
    form.value.visibility = row.visibility || "all";
    const defaults = type === "email" ? defaultEmailData() : defaultBotData();
    form.value.botData = { ...defaults, ...(row.webhook_bots || {}) };
  } else {
    form.value.name = "";
    form.value.is_active = true;
    form.value.visibility = "all";
    form.value.botData = type === "email" ? defaultEmailData() : defaultBotData();
  }
  dialogVisible.value = true;
};

const resetForm = () => {
  formRef.value?.resetFields();
  editingId.value = null;
};

const saveConfig = async () => {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  saving.value = true;
  const payload = {
    name: form.value.name,
    config_type: form.value.config_type,
    webhook_bots: { ...form.value.botData },
    is_active: form.value.is_active,
    visibility: form.value.visibility,
  };

  try {
    if (editingId.value) {
      await updateUnifiedNotificationConfig(editingId.value, payload);
      ElMessage.success(t("configuration.notification.messages.updateSuccess"));
    } else {
      await createUnifiedNotificationConfig(payload);
      ElMessage.success(t("configuration.notification.messages.createSuccess"));
    }
    dialogVisible.value = false;
    await loadConfigs();
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || t("configuration.notification.messages.saveFailed"));
  } finally {
    saving.value = false;
  }
};

const toggleActive = async (row) => {
  try {
    await updateUnifiedNotificationConfig(row.id, {
      name: row.name,
      config_type: row.config_type,
      webhook_bots: row.webhook_bots,
      is_active: !row.is_active,
      visibility: row.visibility,
    });
    row.is_active = !row.is_active;
    ElMessage.success(row.is_active
        ? t("configuration.notification.messages.enabled")
        : t("configuration.notification.messages.disabled"));
  } catch {
    ElMessage.error(t("configuration.notification.messages.operationFailed"));
  }
};

const deleteConfig = async (row) => {
  try {
    await ElMessageBox.confirm(
      t("configuration.notification.messages.deleteConfirm", { name: row.name }),
      t("configuration.notification.messages.deleteConfirmTitle"),
      {
      type: "warning",
        confirmButtonText: t("common.delete"),
        confirmButtonClass: "el-button--danger",
      },
    );
    await deleteUnifiedNotificationConfig(row.id);
    ElMessage.success(t("configuration.notification.messages.deleteSuccess"));
    await loadConfigs();
  } catch (err) {
    if (err !== "cancel") ElMessage.error(t("configuration.notification.messages.deleteFailed"));
  }
};

onMounted(loadConfigs);
</script>

<style scoped>
.notification-config-page {
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
  padding: 0 16px 16px;
}

.bot-tabs {
  margin-top: 8px;
}

.section-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 14px;
  padding-top: 16px;
}

.url-text {
  font-family: monospace;
  font-size: 12px;
  color: #606266;
}

.form-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
