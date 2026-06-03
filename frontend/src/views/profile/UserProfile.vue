<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t("profile.title") }}</h1>
    </div>

    <div class="card-container">
      <el-tabs v-model="activeTab">
        <el-tab-pane :label="$t('profile.basicInfo')" name="basic">
          <el-form
            v-if="userStore.user"
            :model="userStore.user"
            label-width="100px"
          >
            <el-form-item :label="$t('profile.username')">
              <el-input v-model="userStore.user.username" disabled />
            </el-form-item>
            <el-form-item :label="$t('profile.email')">
              <el-input v-model="userStore.user.email" />
            </el-form-item>
            <el-form-item :label="$t('profile.name')">
              <el-input v-model="userStore.user.first_name" />
            </el-form-item>
            <el-form-item :label="$t('profile.department')">
              <el-input v-model="userStore.user.department" />
            </el-form-item>
            <el-form-item :label="$t('profile.position')">
              <el-input v-model="userStore.user.position" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary">{{ $t("common.save") }}</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane :label="$t('profile.changePassword')" name="password">
          <el-form label-width="120px">
            <el-form-item :label="$t('profile.currentPassword')">
              <el-input type="password" />
            </el-form-item>
            <el-form-item :label="$t('profile.newPassword')">
              <el-input type="password" />
            </el-form-item>
            <el-form-item :label="$t('profile.confirmPassword')">
              <el-input type="password" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary">{{
                $t("profile.changePasswordButton")
              }}</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane :label="$t('requirementAnalysis.jira.tabTitle')" name="jira">
          <el-form :model="jiraForm" label-width="120px" style="max-width: 480px; margin-top: 16px">
            <el-form-item :label="$t('requirementAnalysis.jira.domain')">
              <el-input v-model="jiraForm.jira_domain"
                        :placeholder="$t('requirementAnalysis.jira.domainPlaceholder')" />
            </el-form-item>
            <el-form-item :label="$t('requirementAnalysis.jira.email')">
              <el-input v-model="jiraForm.jira_email"
                        :placeholder="$t('requirementAnalysis.jira.emailPlaceholder')" />
            </el-form-item>
            <el-form-item :label="$t('requirementAnalysis.jira.apiToken')">
              <el-input v-model="jiraForm.jira_api_token" type="password" show-password
                        :placeholder="$t('requirementAnalysis.jira.apiTokenPlaceholder')" />
              <div style="font-size:12px; color:#909399; margin-top:4px">
                {{ $t('requirementAnalysis.jira.tokenGuide') }}
              </div>
            </el-form-item>
            <el-form-item>
              <el-button @click="testJiraConnection" :loading="jiraTesting">
                {{ $t('requirementAnalysis.jira.testConnection') }}
              </el-button>
              <el-button type="primary" @click="saveJiraConfig" :loading="jiraSaving">
                {{ $t('requirementAnalysis.jira.save') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { useUserStore } from "@/stores/user";
import request from "@/utils/api";
import { validateJiraConnection } from "@/api/jira";

const { t } = useI18n();
const userStore = useUserStore();
const activeTab = ref("basic");

// Jira 配置
const jiraForm = ref({ jira_domain: '', jira_email: '', jira_api_token: '' });
const jiraTesting = ref(false);
const jiraSaving = ref(false);

const loadJiraConfig = async () => {
  try {
    const res = await request({ url: '/users/profile/', method: 'get' });
    jiraForm.value.jira_domain = res.data.jira_domain || '';
    jiraForm.value.jira_email = res.data.jira_email || '';
  } catch {}
};

const testJiraConnection = async () => {
  jiraTesting.value = true;
  try {
    await validateJiraConnection();
    ElMessage.success(t('requirementAnalysis.jira.connectionSuccess'));
  } catch {
    ElMessage.error(t('requirementAnalysis.jira.connectionFailed'));
  } finally {
    jiraTesting.value = false;
  }
};

const saveJiraConfig = async () => {
  jiraSaving.value = true;
  try {
    await request({
      url: '/users/profile/',
      method: 'patch',
      data: {
        jira_domain: jiraForm.value.jira_domain,
        jira_email: jiraForm.value.jira_email,
        jira_api_token_input: jiraForm.value.jira_api_token,
      }
    });
    ElMessage.success(t('requirementAnalysis.jira.saveSuccess'));
    jiraForm.value.jira_api_token = '';
  } catch {
    ElMessage.error(t('requirementAnalysis.jira.saveFailed'));
  } finally {
    jiraSaving.value = false;
  }
};

onMounted(() => {
  loadJiraConfig();
});
</script>
