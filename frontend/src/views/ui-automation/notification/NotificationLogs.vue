<template>
  <div class="notification-logs-container">
    <!-- 页面操作栏 -->
    <div class="page-actions">
      <el-row :gutter="20" class="filter-row">
        <el-col :span="6">
          <el-input
            v-model="searchForm.taskName"
            :placeholder="$t('uiAutomation.notification.logs.searchTaskName')"
            clearable
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <el-icon>
                <Search />
              </el-icon>
            </template>
          </el-input>
        </el-col>
        <el-col :span="6">
          <el-date-picker
            v-model="searchForm.dateRange"
            type="daterange"
            :range-separator="$t('uiAutomation.notification.logs.dateRangeTo')"
            :start-placeholder="$t('uiAutomation.notification.logs.startDate')"
            :end-placeholder="$t('uiAutomation.notification.logs.endDate')"
            value-format="YYYY-MM-DD"
            @change="handleSearch"
          />
        </el-col>
        <el-col :span="6">
          <el-select
            v-model="searchForm.status"
            :placeholder="
              $t('uiAutomation.notification.logs.notificationStatus')
            "
            clearable
            @change="handleSearch"
          >
            <el-option
              :label="$t('uiAutomation.notification.logs.allStatus')"
              value=""
            />
            <el-option
              :label="$t('uiAutomation.notification.logs.statusSuccess')"
              value="SUCCESS"
            />
            <el-option
              :label="$t('uiAutomation.notification.logs.statusFailed')"
              value="FAILED"
            />
            <el-option
              :label="$t('uiAutomation.notification.logs.statusRetrying')"
              value="RETRYING"
            />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-button type="primary" @click="handleSearch">
            <el-icon>
              <Search />
            </el-icon>
            {{ $t("uiAutomation.common.search") }}
          </el-button>
          <el-button @click="handleReset">
            {{ $t("uiAutomation.common.reset") }}
          </el-button>
        </el-col>
      </el-row>
    </div>

    <!-- 通知列表 -->
    <div class="logs-table-container">
      <el-table
        :data="logsData"
        v-loading="loading"
        :element-loading-text="
          $t('uiAutomation.notification.logs.messages.loading')
        "
        stripe
        style="width: 100%"
        @sort-change="handleSortChange"
      >
        <el-table-column
          prop="task_name"
          :label="$t('uiAutomation.notification.logs.taskName')"
          min-width="150"
          sortable="custom"
        />
        <el-table-column
          prop="task_type_display"
          :label="$t('uiAutomation.notification.logs.taskType')"
          min-width="100"
        >
          <template #default="{ row }">
            <el-tag type="info" size="small">
              {{ row.task_type_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="actual_notification_type_display"
          :label="$t('uiAutomation.notification.logs.notificationType')"
          min-width="120"
        >
          <template #default="{ row }">
            <el-tag
              :type="
                getNotificationTypeTagType(row.actual_notification_type_display)
              "
              size="small"
            >
              {{ row.actual_notification_type_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          :label="$t('uiAutomation.notification.logs.notificationTime')"
          min-width="180"
          sortable="custom"
        >
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="status_display"
          :label="$t('uiAutomation.common.status')"
          min-width="100"
          sortable="custom"
        >
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status_display)" size="small">
              {{ row.status_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('uiAutomation.common.operation')"
          fixed="right"
          width="100"
          align="center"
        >
          <template #default="{ row }">
            <div class="action-col">
              <el-button link type="primary" size="small" @click="viewDetail(row)">
                {{ $t("uiAutomation.notification.logs.viewDetail") }}
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.currentPage"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog
      v-model="detailDialogVisible"
      :title="$t('uiAutomation.notification.logs.detailTitle')"
      width="600px"
      :before-close="handleDetailDialogClose"
    >
      <el-form
        v-if="selectedLog"
        label-position="top"
        class="notification-detail-form"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item
              :label="$t('uiAutomation.notification.logs.taskName')"
            >
              <span>{{ selectedLog.task_name }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="$t('uiAutomation.notification.logs.taskType')"
            >
              <span>{{ selectedLog.task_type_display }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="$t('uiAutomation.notification.logs.notificationType')"
            >
              <el-tag
                :type="
                  getNotificationTypeTagType(
                    selectedLog.actual_notification_type_display,
                  )
                "
              >
                {{ selectedLog.actual_notification_type_display }}
              </el-tag>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="$t('uiAutomation.common.status')">
              <el-tag :type="getStatusTagType(selectedLog.status_display)">
                {{ selectedLog.status_display }}
              </el-tag>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="$t('uiAutomation.notification.logs.notificationTime')"
            >
              <span>{{ formatDate(selectedLog.created_at) }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="$t('uiAutomation.notification.logs.sentTime')"
            >
              <span>{{
                selectedLog.sent_at ? formatDate(selectedLog.sent_at) : "-"
              }}</span>
            </el-form-item>
          </el-col>
          <el-col
            :span="24"
            v-if="
              selectedLog.webhook_bot_info &&
              (selectedLog.webhook_bot_info.bot_type ||
                selectedLog.webhook_bot_info.type)
            "
          >
            <el-form-item
              :label="$t('uiAutomation.notification.logs.webhookBot')"
            >
              <div class="webhook-info">
                <el-tag class="webhook-tag" size="small" type="info">
                  {{
                    selectedLog.webhook_bot_info.name ||
                    selectedLog.webhook_bot_info.bot_name ||
                    $t("uiAutomation.notification.logs.defaultBotName")
                  }}
                </el-tag>
              </div>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item :label="$t('uiAutomation.notification.logs.content')">
              <NotificationContentView
                :content="selectedLog.notification_content"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24" v-if="selectedLog.error_message">
            <el-form-item
              :label="$t('uiAutomation.notification.logs.errorMessage')"
            >
              <div class="error-message">
                <el-alert
                  :title="selectedLog.error_message"
                  type="error"
                  show-icon
                  :closable="false"
                />
              </div>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="detailDialogVisible = false">{{
            $t("uiAutomation.common.close")
          }}</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { Search } from "@element-plus/icons-vue";
import NotificationContentView from "@/components/notification/NotificationContentView.vue";
import { ref, reactive, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { getNotificationLogs } from "@/api/ui_automation.js";
import { useI18n } from "vue-i18n";

export default {
  name: "NotificationLogs",
  components: {
    Search,
    NotificationContentView,
  },
  setup() {
    const { t, locale } = useI18n();

    // 数据状态
    const loading = ref(false);
    const logsData = ref([]);
    const detailDialogVisible = ref(false);
    const selectedLog = ref(null);

    // 搜索表单
    const searchForm = reactive({
      taskName: "",
      dateRange: [],
      status: "",
    });

    // 分页配置
    const pagination = reactive({
      currentPage: 1,
      pageSize: 10,
      total: 0,
    });

    // 排序参数
    const sortParams = reactive({
      prop: "created_at",
      order: "descending",
    });

    // 获取通知日志数据
    const fetchLogsData = async () => {
      loading.value = true;
      try {
        const params = {
          page: pagination.currentPage,
          page_size: pagination.pageSize,
          ordering:
            sortParams.order === "ascending"
              ? sortParams.prop
              : `-${sortParams.prop}`,
        };

        // 添加搜索条件
        if (searchForm.taskName) {
          params.search = searchForm.taskName;
        }
        if (searchForm.dateRange && searchForm.dateRange.length === 2) {
          params.start_date = searchForm.dateRange[0];
          params.end_date = searchForm.dateRange[1];
        }
        if (searchForm.status) {
          params.status = searchForm.status;
        }

        const response = await getNotificationLogs(params);
        logsData.value = response.data.results || [];
        pagination.total = response.data.count || 0;
      } catch (error) {
        console.error("Failed to fetch notification logs:", error);
        ElMessage.error(
          t("uiAutomation.notification.logs.messages.loadFailed"),
        );
      } finally {
        loading.value = false;
      }
    };

    // 处理搜索
    const handleSearch = () => {
      pagination.currentPage = 1;
      fetchLogsData();
    };

    // 重置搜索
    const handleReset = () => {
      searchForm.taskName = "";
      searchForm.dateRange = [];
      searchForm.status = "";
      pagination.currentPage = 1;
      fetchLogsData();
    };

    // 处理分页变化
    const handleSizeChange = (val) => {
      pagination.pageSize = val;
      pagination.currentPage = 1;
      fetchLogsData();
    };

    const handleCurrentChange = (val) => {
      pagination.currentPage = val;
      fetchLogsData();
    };

    // 处理排序
    const handleSortChange = ({ prop, order }) => {
      sortParams.prop = prop;
      sortParams.order = order || "descending";
      fetchLogsData();
    };

    // 查看详情
    const viewDetail = (row) => {
      selectedLog.value = row;
      detailDialogVisible.value = true;
    };

    // 关闭详情弹窗
    const handleDetailDialogClose = (done) => {
      selectedLog.value = null;
      done();
    };

    // 格式化日期
    const formatDate = (dateString) => {
      if (!dateString) return "-";
      const date = new Date(dateString);
      return date.toLocaleString(locale.value === "zh-cn" ? "zh-CN" : "en-US");
    };

    // 获取状态标签类型
    const getStatusTagType = (status) => {
      const typeMap = {
        // Chinese
        发送成功: "success",
        发送失败: "danger",
        待发送: "info",
        发送中: "warning",
        已取消: "info",
        // English
        Success: "success",
        Failed: "danger",
        Pending: "info",
        Sending: "warning",
        Cancelled: "info",
        // Lowercase
        success: "success",
        failed: "danger",
        pending: "info",
        sending: "warning",
        cancelled: "info",
      };
      return typeMap[status] || "info";
    };

    // 获取通知类型标签类型
    const getNotificationTypeTagType = (typeDisplay) => {
      const typeMap = {
        // Chinese
        邮箱通知: "",
        Webhook机器人: "primary",
        两种都发送: "warning",
        // English
        Email: "",
        "Webhook Bot": "primary",
        Both: "warning",
      };
      return typeMap[typeDisplay] || "info";
    };

    // 组件挂载时获取数据
    onMounted(() => {
      fetchLogsData();
    });

    return {
      loading,
      logsData,
      detailDialogVisible,
      selectedLog,
      searchForm,
      pagination,
      sortParams,
      handleSearch,
      handleReset,
      handleSizeChange,
      handleCurrentChange,
      handleSortChange,
      viewDetail,
      handleDetailDialogClose,
      formatDate,
      getStatusTagType,
      getNotificationTypeTagType,
    };
  },
};
</script>

<style scoped>
.notification-logs-container {
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.page-actions {
  margin-bottom: 20px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 6px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 15px;
}

.logs-table-container {
  margin-top: 20px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.notification-detail-form :deep(.el-form-item) {
  margin-bottom: 18px;
}

.webhook-info {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.webhook-tag {
  margin: 0;
}

.error-message {
  margin-top: 8px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
