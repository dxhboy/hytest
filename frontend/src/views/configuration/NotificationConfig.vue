<template>
  <div class="notification-config-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-left">
        <el-icon class="title-icon"><Bell /></el-icon>
        <div>
          <h2 class="page-title">通知配置</h2>
          <p class="page-desc">管理机器人通知渠道和邮件配置，支持多条独立配置，可控制可见范围</p>
        </div>
      </div>
    </div>

    <!-- 主 Tab -->
    <div class="main-card">
      <el-tabs v-model="mainTab">
        <!-- Tab 1: 机器人通知 -->
        <el-tab-pane label="机器人通知" name="bot">
          <el-tabs v-model="botTab" type="card" class="bot-tabs">
            <!-- 飞书 -->
            <el-tab-pane name="webhook_feishu" label="飞书机器人 (Lark)">
              <div class="section-toolbar">
                <el-button type="primary" @click="openDialog('webhook_feishu')">
                  <el-icon><Plus /></el-icon>新增飞书机器人
                </el-button>
              </div>
              <el-table :data="botsByType('webhook_feishu')" v-loading="loading" border style="width:100%">
                <el-table-column prop="name" label="配置名称" min-width="140" show-overflow-tooltip />
                <el-table-column label="Webhook URL" min-width="260" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="url-text">{{ row.webhook_bots?.webhook_url || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="签名密钥" width="90" align="center">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.webhook_bots?.secret ? 'success' : 'info'">
                      {{ row.webhook_bots?.secret ? '已配置' : '未配置' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="业务范围" width="160" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.webhook_bots?.enable_api_testing" size="small" style="margin-right:4px">接口测试</el-tag>
                    <el-tag v-if="row.webhook_bots?.enable_ui_automation" size="small" type="warning">UI自动化</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="80" align="center">
                  <template #default="{ row }">
                    <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
                  </template>
                </el-table-column>
                <el-table-column label="可见性" width="120" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.visibility === 'all' ? 'success' : 'warning'" size="small">
                      {{ row.visibility === 'all' ? '所有人可见' : '仅自己可见' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="创建者" width="100" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.created_by_name }}</template>
                </el-table-column>
                <el-table-column label="操作" width="130" align="center" fixed="right">
                  <template #default="{ row }">
                    <el-button text type="primary" size="small" @click="openDialog('webhook_feishu', row)">编辑</el-button>
                    <el-button text type="danger" size="small" @click="deleteConfig(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 企业微信 -->
            <el-tab-pane name="webhook_wechat" label="企业微信机器人">
              <div class="section-toolbar">
                <el-button type="primary" @click="openDialog('webhook_wechat')">
                  <el-icon><Plus /></el-icon>新增企业微信机器人
                </el-button>
              </div>
              <el-table :data="botsByType('webhook_wechat')" v-loading="loading" border style="width:100%">
                <el-table-column prop="name" label="配置名称" min-width="140" show-overflow-tooltip />
                <el-table-column label="Webhook URL" min-width="280" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="url-text">{{ row.webhook_bots?.webhook_url || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="业务范围" width="160" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.webhook_bots?.enable_api_testing" size="small" style="margin-right:4px">接口测试</el-tag>
                    <el-tag v-if="row.webhook_bots?.enable_ui_automation" size="small" type="warning">UI自动化</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="80" align="center">
                  <template #default="{ row }">
                    <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
                  </template>
                </el-table-column>
                <el-table-column label="可见性" width="120" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.visibility === 'all' ? 'success' : 'warning'" size="small">
                      {{ row.visibility === 'all' ? '所有人可见' : '仅自己可见' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="创建者" width="100" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.created_by_name }}</template>
                </el-table-column>
                <el-table-column label="操作" width="130" align="center" fixed="right">
                  <template #default="{ row }">
                    <el-button text type="primary" size="small" @click="openDialog('webhook_wechat', row)">编辑</el-button>
                    <el-button text type="danger" size="small" @click="deleteConfig(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <!-- 钉钉 -->
            <el-tab-pane name="webhook_dingtalk" label="钉钉机器人">
              <div class="section-toolbar">
                <el-button type="primary" @click="openDialog('webhook_dingtalk')">
                  <el-icon><Plus /></el-icon>新增钉钉机器人
                </el-button>
              </div>
              <el-table :data="botsByType('webhook_dingtalk')" v-loading="loading" border style="width:100%">
                <el-table-column prop="name" label="配置名称" min-width="140" show-overflow-tooltip />
                <el-table-column label="Webhook URL" min-width="260" show-overflow-tooltip>
                  <template #default="{ row }">
                    <span class="url-text">{{ row.webhook_bots?.webhook_url || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="签名密钥" width="90" align="center">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.webhook_bots?.secret ? 'success' : 'info'">
                      {{ row.webhook_bots?.secret ? '已配置' : '未配置' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="业务范围" width="160" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.webhook_bots?.enable_api_testing" size="small" style="margin-right:4px">接口测试</el-tag>
                    <el-tag v-if="row.webhook_bots?.enable_ui_automation" size="small" type="warning">UI自动化</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="80" align="center">
                  <template #default="{ row }">
                    <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
                  </template>
                </el-table-column>
                <el-table-column label="可见性" width="120" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.visibility === 'all' ? 'success' : 'warning'" size="small">
                      {{ row.visibility === 'all' ? '所有人可见' : '仅自己可见' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="创建者" width="100" show-overflow-tooltip>
                  <template #default="{ row }">{{ row.created_by_name }}</template>
                </el-table-column>
                <el-table-column label="操作" width="130" align="center" fixed="right">
                  <template #default="{ row }">
                    <el-button text type="primary" size="small" @click="openDialog('webhook_dingtalk', row)">编辑</el-button>
                    <el-button text type="danger" size="small" @click="deleteConfig(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>

        <!-- Tab 2: 邮件配置 -->
        <el-tab-pane label="邮件配置" name="email">
          <div class="section-toolbar">
            <el-button type="primary" @click="openDialog('email')">
              <el-icon><Plus /></el-icon>新增邮件配置
            </el-button>
          </div>
          <el-table :data="botsByType('email')" v-loading="loading" border style="width:100%">
            <el-table-column prop="name" label="配置名称" min-width="140" show-overflow-tooltip />
            <el-table-column label="SMTP服务器" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.webhook_bots?.host || '-' }}{{ row.webhook_bots?.port ? ':' + row.webhook_bots.port : '' }}
              </template>
            </el-table-column>
            <el-table-column label="发件人账号" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.webhook_bots?.username || '-' }}</template>
            </el-table-column>
            <el-table-column label="TLS" width="70" align="center">
              <template #default="{ row }">
                <el-tag :type="row.webhook_bots?.use_tls ? 'success' : 'info'" size="small">
                  {{ row.webhook_bots?.use_tls ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-switch :model-value="row.is_active" @change="toggleActive(row)" />
              </template>
            </el-table-column>
            <el-table-column label="可见性" width="120" align="center">
              <template #default="{ row }">
                <el-tag :type="row.visibility === 'all' ? 'success' : 'warning'" size="small">
                  {{ row.visibility === 'all' ? '所有人可见' : '仅自己可见' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建者" width="100" show-overflow-tooltip>
              <template #default="{ row }">{{ row.created_by_name }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" align="center" fixed="right">
              <template #default="{ row }">
                <el-button text type="primary" size="small" @click="openDialog('email', row)">编辑</el-button>
                <el-button text type="danger" size="small" @click="deleteConfig(row)">删除</el-button>
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
        <el-form-item label="配置名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入配置名称" clearable />
        </el-form-item>

        <!-- 机器人字段 -->
        <template v-if="form.config_type !== 'email'">
          <el-form-item label="Webhook URL" prop="webhook_url">
            <el-input
              v-model="form.botData.webhook_url"
              :placeholder="webhookPlaceholder"
              clearable
            />
          </el-form-item>
          <el-form-item v-if="form.config_type !== 'webhook_wechat'" label="签名密钥">
            <el-input
              v-model="form.botData.secret"
              placeholder="可选，用于消息签名验证"
              type="password"
              show-password
              clearable
            />
          </el-form-item>
          <el-form-item label="业务范围">
            <el-checkbox v-model="form.botData.enable_api_testing">接口测试通知</el-checkbox>
            <el-checkbox v-model="form.botData.enable_ui_automation">UI自动化通知</el-checkbox>
          </el-form-item>
        </template>

        <!-- 邮件字段 -->
        <template v-else>
          <el-form-item label="SMTP服务器" prop="smtp_host">
            <el-input v-model="form.botData.host" placeholder="例：smtp.qq.com" clearable />
          </el-form-item>
          <el-form-item label="SMTP端口" prop="smtp_port">
            <el-input-number v-model="form.botData.port" :min="1" :max="65535" style="width:100%" />
          </el-form-item>
          <el-form-item label="用户名" prop="smtp_username">
            <el-input v-model="form.botData.username" placeholder="邮箱账号或用户名" clearable />
          </el-form-item>
          <el-form-item label="密码/授权码">
            <el-input
              v-model="form.botData.password"
              placeholder="邮箱密码或授权码"
              type="password"
              show-password
              clearable
            />
          </el-form-item>
          <el-form-item label="发件人邮箱">
            <el-input
              v-model="form.botData.from_email"
              placeholder="发件人地址，默认同用户名"
              clearable
            />
          </el-form-item>
          <el-form-item label="使用TLS">
            <el-switch v-model="form.botData.use_tls" />
          </el-form-item>
        </template>

        <!-- 公共字段 -->
        <el-divider />
        <el-form-item label="启用状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
        <el-form-item label="可见范围">
          <el-radio-group v-model="form.visibility">
            <el-radio value="all">所有人可见可用</el-radio>
            <el-radio value="private">仅自己可见可用</el-radio>
          </el-radio-group>
          <div class="form-hint">私有配置只有你自己能看到和使用</div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveConfig" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Bell, Plus } from "@element-plus/icons-vue";
import {
  getUnifiedNotificationConfigs,
  createUnifiedNotificationConfig,
  updateUnifiedNotificationConfig,
  deleteUnifiedNotificationConfig,
} from "@/api/core.js";

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
    name: [{ required: true, message: "请输入配置名称", trigger: "blur" }],
  };
  if (form.value.config_type !== "email") {
    rules.webhook_url = [{ required: true, message: "请输入 Webhook URL", trigger: "blur" }];
  } else {
    rules.smtp_host = [{ required: true, message: "请输入 SMTP 服务器", trigger: "blur" }];
    rules.smtp_port = [{ required: true, message: "请输入端口", trigger: "blur" }];
    rules.smtp_username = [{ required: true, message: "请输入用户名", trigger: "blur" }];
  }
  return rules;
});

const TYPE_LABEL = {
  webhook_feishu: "飞书机器人",
  webhook_wechat: "企业微信机器人",
  webhook_dingtalk: "钉钉机器人",
  email: "邮件配置",
};

const WEBHOOK_PLACEHOLDER = {
  webhook_feishu: "https://open.feishu.cn/open-apis/bot/v2/hook/...",
  webhook_wechat: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...",
  webhook_dingtalk: "https://oapi.dingtalk.com/robot/send?access_token=...",
};

const dialogTitle = computed(() => {
  const typeName = TYPE_LABEL[form.value.config_type] || "";
  return editingId.value ? `编辑 ${typeName}` : `新增 ${typeName}`;
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
    ElMessage.error("加载通知配置失败");
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
      ElMessage.success("更新成功");
    } else {
      await createUnifiedNotificationConfig(payload);
      ElMessage.success("创建成功");
    }
    dialogVisible.value = false;
    await loadConfigs();
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || "保存失败");
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
    ElMessage.success(row.is_active ? "已启用" : "已禁用");
  } catch {
    ElMessage.error("操作失败");
  }
};

const deleteConfig = async (row) => {
  try {
    await ElMessageBox.confirm(`确认删除「${row.name}」？`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      confirmButtonClass: "el-button--danger",
    });
    await deleteUnifiedNotificationConfig(row.id);
    ElMessage.success("删除成功");
    await loadConfigs();
  } catch (err) {
    if (err !== "cancel") ElMessage.error("删除失败");
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
