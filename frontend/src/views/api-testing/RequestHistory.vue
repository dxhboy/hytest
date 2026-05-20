<template>
  <div class="request-history">
    <div class="header">
      <h3>{{ $t("apiTesting.history.title") }}</h3>
      <div class="filters">
        <el-input
          v-model="searchText"
          :placeholder="$t('apiTesting.history.searchRequest')"
          style="width: 200px"
          clearable
          @input="loadHistory"
        />
        <el-button
          type="danger"
          :disabled="selectedIds.length === 0"
          @click="handleBatchDelete"
        >
          {{ $t("apiTesting.history.batchDelete") }}
        </el-button>
        <el-button @click="clearHistory" type="danger" plain>
          {{ $t("apiTesting.history.clearHistory") }}
        </el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane :label="$t('apiTesting.history.httpRequest')" name="HTTP">
        <HistoryTable
          :data="httpHistory"
          :loading="loading"
          @view-detail="viewDetail"
          @retry-request="retryRequest"
          @selection-change="handleSelectionChange"
          @delete-item="handleDelete"
        />
      </el-tab-pane>
      <el-tab-pane
        :label="$t('apiTesting.history.websocketRequest')"
        name="WEBSOCKET"
      >
        <HistoryTable
          :data="websocketHistory"
          :loading="loading"
          @view-detail="viewDetail"
          @retry-request="retryRequest"
          @selection-change="handleSelectionChange"
          @delete-item="handleDelete"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      :total="total"
      layout="total, sizes, prev, pager, next, jumper"
      @size-change="handleSizeChange"
      @current-change="handleCurrentChange"
      class="pagination"
    />

    <!-- 详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      :title="$t('apiTesting.history.requestDetail')"
      width="80%"
      :top="'5vh'"
    >
      <div v-if="selectedHistory" class="history-detail">
        <el-descriptions
          :title="$t('apiTesting.history.basicInfo')"
          :column="2"
          border
        >
          <el-descriptions-item :label="$t('apiTesting.interface.requestName')">
            {{ selectedHistory.request.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('apiTesting.history.requestMethod')">
            <el-tag :type="getMethodType(selectedHistory.request.method)">
              {{ selectedHistory.request.method }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('apiTesting.history.statusCode')">
            <el-tag :type="getStatusType(selectedHistory.status_code)">
              {{
                selectedHistory.status_code ||
                $t("apiTesting.history.noResponse")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('apiTesting.history.responseTime')">
            {{ selectedHistory.response_time?.toFixed(0) || 0 }}ms
          </el-descriptions-item>
          <el-descriptions-item :label="$t('apiTesting.history.executionTime')">
            {{ formatDate(selectedHistory.executed_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('apiTesting.history.executor')">
            {{ selectedHistory.executed_by.username }}
          </el-descriptions-item>
        </el-descriptions>

        <el-tabs v-model="detailTab" class="detail-tabs">
          <el-tab-pane
            :label="$t('apiTesting.history.requestInfo')"
            name="request"
          >
            <div class="detail-section">
              <h4>{{ $t("apiTesting.history.requestUrl") }}</h4>
              <el-input v-model="selectedHistory.request_data.url" readonly />

              <h4>{{ $t("apiTesting.history.requestHeaders") }}</h4>
              <el-table
                :data="formatHeaders(selectedHistory.request_data.headers)"
                style="width: 100%"
              >
                <el-table-column prop="key" label="Key" width="200" />
                <el-table-column prop="value" label="Value" />
              </el-table>

              <h4
                v-if="
                  selectedHistory.request_data.params &&
                  Object.keys(selectedHistory.request_data.params).length > 0
                "
              >
                {{ $t("apiTesting.history.requestParams") }}
              </h4>
              <el-table
                v-if="
                  selectedHistory.request_data.params &&
                  Object.keys(selectedHistory.request_data.params).length > 0
                "
                :data="formatHeaders(selectedHistory.request_data.params)"
                style="width: 100%"
              >
                <el-table-column prop="key" label="Key" width="200" />
                <el-table-column prop="value" label="Value" />
              </el-table>

              <h4 v-if="selectedHistory.request_data.body">
                {{ $t("apiTesting.history.requestBody") }}
              </h4>
              <pre
                v-if="selectedHistory.request_data.body"
                class="json-content"
              >
                {{ JSON.stringify(selectedHistory.request_data.body, null, 2) }}
              </pre>
            </div>
          </el-tab-pane>

          <el-tab-pane
            :label="$t('apiTesting.history.responseInfo')"
            name="response"
          >
            <div v-if="selectedHistory.response_data" class="detail-section">
              <h4>{{ $t("apiTesting.history.responseHeaders") }}</h4>
              <el-table
                :data="formatHeaders(selectedHistory.response_data.headers)"
                style="width: 100%"
              >
                <el-table-column prop="key" label="Key" width="200" />
                <el-table-column prop="value" label="Value" />
              </el-table>

              <h4>{{ $t("apiTesting.history.responseBody") }}</h4>
              <div class="response-actions">
                <el-button size="small" @click="formatResponseBody">{{
                  $t("apiTesting.interface.format")
                }}</el-button>
                <el-button size="small" @click="copyResponseBody">{{
                  $t("apiTesting.common.copy")
                }}</el-button>
              </div>
              <pre class="json-content">{{ responseBodyText }}</pre>
            </div>

            <div
              v-else-if="selectedHistory.error_message"
              class="error-section"
            >
              <h4>{{ $t("apiTesting.automation.status.failed") }}</h4>
              <el-alert
                :title="selectedHistory.error_message"
                type="error"
                :closable="false"
                show-icon
              />
            </div>

            <div v-else class="empty-response">
              <el-empty
                :description="$t('apiTesting.history.noResponseData')"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane
            :label="$t('apiTesting.history.assertionResults')"
            name="assertions"
          >
            <div v-if="selectedHistory.assertions_results && selectedHistory.assertions_results.length > 0" class="assertions-results">
              <div
                v-for="(result, index) in selectedHistory.assertions_results"
                :key="index"
                class="assertion-result-item"
                :class="{ passed: result.passed, failed: !result.passed }"
              >
                <div class="assertion-result-header">
                  <el-tag :type="result.passed ? 'success' : 'danger'" size="small">
                    {{ result.passed ? $t('apiTesting.interface.passed') : $t('apiTesting.interface.failed') }}
                  </el-tag>
                  <span class="assertion-name">{{ result.name }}</span>
                </div>
                <div class="assertion-result-details">
                  <div class="result-row">
                    <span class="label">{{ $t('apiTesting.interface.expected') }}</span>
                    <span class="value">{{ formatAssertionValue(result.expected) }}</span>
                  </div>
                  <div class="result-row">
                    <span class="label">{{ $t('apiTesting.interface.actual') }}</span>
                    <span class="value">{{ formatAssertionValue(result.actual) }}</span>
                  </div>
                  <div class="result-row" v-if="result.error">
                    <span class="label">{{ $t('apiTesting.interface.error') }}</span>
                    <span class="value error">{{ result.error }}</span>
                  </div>
                  <div v-if="result.mongo_result" class="mongo-result-detail">
                    <div class="mongo-result-summary">
                      <el-tag type="info" size="small">{{ $t('apiTesting.interface.mongoTotal') }}: {{ result.mongo_result.total }}</el-tag>
                      <el-tag type="success" size="small">{{ $t('apiTesting.interface.mongoPassed') }}: {{ result.mongo_result.successful_count }}</el-tag>
                      <el-tag :type="result.mongo_result.failed_count > 0 ? 'danger' : 'info'" size="small">{{ $t('apiTesting.interface.mongoFailed') }}: {{ result.mongo_result.failed_count }}</el-tag>
                    </div>
                    <div v-if="result.mongo_result.failed_matches && result.mongo_result.failed_matches.length > 0" class="mongo-failed-matches">
                      <div v-for="(match, mi) in result.mongo_result.failed_matches" :key="mi" class="mongo-match-row failed">
                        <span class="mongo-path">{{ match.path }}</span>
                        <span class="mongo-op">{{ match.operator }}</span>
                        <span class="mongo-expected">{{ $t('apiTesting.interface.expected') }}: {{ formatAssertionValue(match.expected) }}</span>
                        <span class="mongo-actual">{{ $t('apiTesting.interface.actual') }}: {{ formatAssertionValue(match.actual) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="empty-response">
              <el-empty :description="$t('apiTesting.history.noAssertionData')" />
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>

      <template #footer>
        <el-button @click="showDetailDialog = false">{{
          $t("apiTesting.common.close")
        }}</el-button>
        <el-button type="primary" @click="retryRequest(selectedHistory)">
          {{ $t("apiTesting.history.retryRequest") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import api from "@/utils/api";
import {
  deleteRequestHistory,
  batchDeleteRequestHistory,
} from "@/api/api-testing";
import dayjs from "dayjs";
import HistoryTable from "./components/HistoryTable.vue";

const { t } = useI18n();
const activeTab = ref("HTTP");
const httpHistory = ref([]);
const websocketHistory = ref([]);
const loading = ref(false);
const searchText = ref("");
const currentPage = ref(1);
const pageSize = ref(20);
const total = ref(0);
const showDetailDialog = ref(false);
const selectedHistory = ref(null);
const detailTab = ref("request");
const selectedIds = ref([]);

const currentHistory = computed(() => {
  return activeTab.value === "HTTP"
    ? httpHistory.value
    : websocketHistory.value;
});

const responseBodyText = computed(() => {
  if (!selectedHistory.value?.response_data) return "";

  try {
    if (selectedHistory.value.response_data.json) {
      return JSON.stringify(selectedHistory.value.response_data.json, null, 2);
    } else {
      return selectedHistory.value.response_data.body || "";
    }
  } catch (e) {
    return selectedHistory.value.response_data.body || "";
  }
});

const getMethodType = (method) => {
  const typeMap = {
    GET: "success",
    POST: "primary",
    PUT: "warning",
    DELETE: "danger",
    PATCH: "info",
  };
  return typeMap[method] || "info";
};

const getStatusType = (status) => {
  if (!status) return "info";
  if (status >= 200 && status < 300) return "success";
  if (status >= 300 && status < 400) return "warning";
  if (status >= 400) return "danger";
  return "info";
};

const formatDate = (dateString) => {
  return dayjs(dateString).format("YYYY-MM-DD HH:mm:ss");
};

const formatHeaders = (headers) => {
  if (!headers || typeof headers !== "object") return [];
  return Object.keys(headers).map((key) => ({
    key,
    value: headers[key],
  }));
};

const loadHistory = async () => {
  loading.value = true;
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      request__request_type: activeTab.value,
    };

    if (searchText.value) {
      params.search = searchText.value;
    }

    const response = await api.get("/api-testing/histories/", { params });
    const data = response.data.results || response.data;

    if (activeTab.value === "HTTP") {
      httpHistory.value = data;
    } else {
      websocketHistory.value = data;
    }

    total.value = response.data.count || data.length;
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.loadHistory"));
    console.error(error);
  } finally {
    loading.value = false;
  }
};

const onTabChange = () => {
  currentPage.value = 1;
  selectedIds.value = [];
  loadHistory();
};

const handleSizeChange = (size) => {
  pageSize.value = size;
  loadHistory();
};

const handleCurrentChange = (page) => {
  currentPage.value = page;
  loadHistory();
};

const viewDetail = (history) => {
  selectedHistory.value = history;
  detailTab.value = "request";
  showDetailDialog.value = true;
};

const retryRequest = async (history) => {
  try {
    const response = await api.post(
      `/api-testing/requests/${history.request.id}/execute/`,
      {
        environment_id: history.environment?.id,
      },
    );
    ElMessage.success(t("apiTesting.messages.success.requestRetried"));
    showDetailDialog.value = false;
    await loadHistory();
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.sendFailed"));
    console.error(error);
  }
};

const clearHistory = async () => {
  try {
    await ElMessageBox.confirm(
      t("apiTesting.history.confirmClearHistory"),
      t("apiTesting.messages.confirm.clearTitle"),
      {
        confirmButtonText: t("apiTesting.common.confirm"),
        cancelButtonText: t("apiTesting.common.cancel"),
        type: "warning",
      },
    );
    await api.delete("/api-testing/histories/clear/", {
      params: { request_type: activeTab.value },
    });
    ElMessage.success(t("apiTesting.history.clearSuccess"));
    loadHistory();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(t("apiTesting.history.clearFailed"));
      console.error(error);
    }
  }
};

const handleSelectionChange = (selection) => {
  selectedIds.value = selection.map((item) => item.id);
};

const handleDelete = (row) => {
  ElMessageBox.confirm(
    t("apiTesting.history.confirmDelete"),
    t("apiTesting.common.tip"),
    {
      confirmButtonText: t("apiTesting.common.confirm"),
      cancelButtonText: t("apiTesting.common.cancel"),
      type: "warning",
    },
  ).then(async () => {
    try {
      await deleteRequestHistory(row.id);
      ElMessage.success(t("apiTesting.messages.success.delete"));
      loadHistory();
    } catch (error) {
      console.error("Delete failed:", error);
      ElMessage.error(t("apiTesting.messages.error.deleteFailed"));
    }
  });
};

const handleBatchDelete = () => {
  if (selectedIds.value.length === 0) return;

  ElMessageBox.confirm(
    t("apiTesting.history.confirmBatchDelete", { n: selectedIds.value.length }),
    t("apiTesting.common.tip"),
    {
      confirmButtonText: t("apiTesting.common.confirm"),
      cancelButtonText: t("apiTesting.common.cancel"),
      type: "warning",
    },
  ).then(async () => {
    try {
      await batchDeleteRequestHistory(selectedIds.value);
      ElMessage.success(t("apiTesting.messages.success.batchDeleteSuccess"));
      selectedIds.value = [];
      loadHistory();
    } catch (error) {
      console.error("Batch delete failed:", error);
      ElMessage.error(t("apiTesting.messages.error.batchDeleteFailed"));
    }
  });
};

const formatAssertionValue = (value) => {
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value, null, 2);
  }
  return value;
};

const formatResponseBody = () => {
  if (selectedHistory.value?.response_data?.json) {
    // 已经格式化了
  }
};

const copyResponseBody = () => {
  if (responseBodyText.value) {
    navigator.clipboard.writeText(responseBodyText.value);
    ElMessage.success(t("apiTesting.messages.success.copiedToClipboard"));
  }
};

onMounted(() => {
  loadHistory();
});
</script>

<style scoped>
.request-history {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h3 {
  margin: 0;
  color: #303133;
}

.filters {
  display: flex;
  gap: 10px;
  align-items: center;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}

.history-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.detail-tabs {
  margin-top: 20px;
}

.detail-section {
  padding: 10px 0;
}

.detail-section h4 {
  margin: 20px 0 10px 0;
  color: #303133;
  font-size: 14px;
  font-weight: 600;
}

.json-content {
  background: #f8f9fa;
  padding: 15px;
  border-radius: 4px;
  font-family: "Courier New", monospace;
  font-size: 12px;
  max-height: 400px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  border: 1px solid #e4e7ed;
}

.response-actions {
  margin-bottom: 10px;
}

.error-section {
  padding: 20px 0;
}

.empty-response {
  padding: 40px 0;
  text-align: center;
}

.assertions-results {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 10px 0;
}

.assertion-result-item {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px 16px;
  border-left-width: 4px;
}

.assertion-result-item.passed {
  border-left-color: #67c23a;
  background-color: #f0f9eb;
}

.assertion-result-item.failed {
  border-left-color: #f56c6c;
  background-color: #fef0f0;
}

.assertion-result-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.assertion-name {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.assertion-result-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.result-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
}

.result-row .label {
  color: #909399;
  min-width: 60px;
  flex-shrink: 0;
}

.result-row .value {
  color: #303133;
  word-break: break-all;
  white-space: pre-wrap;
}

.result-row .value.error {
  color: #f56c6c;
}

.mongo-result-detail {
  margin-top: 8px;
}

.mongo-result-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.mongo-failed-matches {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mongo-match-row {
  display: flex;
  gap: 12px;
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 4px;
  flex-wrap: wrap;
}

.mongo-match-row.failed {
  background-color: #fff5f5;
  border: 1px solid #fcd3d3;
}

.mongo-path { color: #606266; font-weight: 600; }
.mongo-op   { color: #909399; }
.mongo-expected { color: #67c23a; }
.mongo-actual   { color: #f56c6c; }
</style>
