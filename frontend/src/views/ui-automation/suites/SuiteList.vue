<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t("uiAutomation.suite.title") }}</h1>
      <el-select
        v-model="projectId"
        :placeholder="$t('uiAutomation.common.selectProject')"
        style="width: 200px; margin-right: 15px"
        @change="onProjectChange"
      >
        <el-option
          v-for="project in projects"
          :key="project.id"
          :label="project.name"
          :value="project.id"
        />
      </el-select>
      <el-button type="primary" @click="handleNewSuite">
        <el-icon><Plus /></el-icon>
        {{ $t("uiAutomation.suite.newSuite") }}
      </el-button>
    </div>

    <div class="card-container">
      <div class="filter-bar">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-input
              v-model="searchText"
              :placeholder="$t('uiAutomation.suite.searchPlaceholder')"
              clearable
              @input="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-col>
        </el-row>
      </div>

      <el-table :data="suites" v-loading="loading" style="width: 100%">
        <el-table-column type="selection" width="55" />
        <el-table-column
          prop="name"
          :label="$t('uiAutomation.suite.suiteName')"
          min-width="200"
        >
          <template #default="{ row }">
            <el-link @click="editSuite(row.id)" type="primary">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column
          prop="description"
          :label="$t('uiAutomation.common.description')"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column
          :label="$t('uiAutomation.suite.testCaseCount')"
          width="100"
        >
          <template #default="{ row }">
            {{ row.test_case_count || 0 }}
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('uiAutomation.suite.scriptCount')"
          width="100"
        >
          <template #default="{ row }">
            {{ row.script_count || 0 }}
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('uiAutomation.suite.executionStatus')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="getExecutionStatusTag(row.execution_status)">
              {{ getExecutionStatusText(row.execution_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('uiAutomation.suite.passedCount')"
          width="90"
        >
          <template #default="{ row }">
            <span style="color: #67c23a; font-weight: bold">{{
              row.passed_count || 0
            }}</span>
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('uiAutomation.suite.failedCount')"
          width="90"
        >
          <template #default="{ row }">
            <span style="color: #f56c6c; font-weight: bold">{{
              row.failed_count || 0
            }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="visibility"
          :label="$t('uiAutomation.common.visibility')"
          width="110"
        >
          <template #default="{ row }">
            <el-tag :type="row.visibility === 'all' ? 'success' : 'info'" size="small">
              {{ row.visibility === 'all' ? $t('uiAutomation.common.visibleAll') : $t('uiAutomation.common.visibleSelf') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_at"
          :label="$t('uiAutomation.common.createTime')"
          width="180"
          :formatter="localeDateTimeFormatter"
        />
        <el-table-column
          prop="updated_at"
          :label="$t('uiAutomation.common.updateTime')"
          width="180"
          :formatter="localeDateTimeFormatter"
        />
        <el-table-column
          :label="$t('uiAutomation.common.operation')"
          width="200"
          fixed="right"
          align="center"
        >
          <template #default="{ row }">
            <div class="action-col">
              <el-button link type="primary" size="small" @click="editSuite(row.id)">
                {{ $t("uiAutomation.common.edit") }}
              </el-button>
              <span class="action-divider" />
              <el-button link type="primary" size="small" @click="runSuite(row)">
                {{ $t("uiAutomation.common.run") }}
              </el-button>
              <span class="action-divider" />
              <el-button link type="danger" size="small" @click="deleteSuite(row.id)">
                {{ $t("uiAutomation.common.delete") }}
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.currentPage"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <!-- 创建/编辑套件对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="
        isEditing
          ? $t('uiAutomation.suite.editSuite')
          : $t('uiAutomation.suite.createSuite')
      "
      width="900px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="formRules"
        label-width="100px"
      >
        <el-form-item :label="$t('uiAutomation.suite.suiteName')" prop="name">
          <el-input
            v-model="createForm.name"
            :placeholder="$t('uiAutomation.suite.rules.nameRequired')"
          />
        </el-form-item>
        <el-form-item
          :label="$t('uiAutomation.common.description')"
          prop="description"
        >
          <el-input
            v-model="createForm.description"
            type="textarea"
            :placeholder="$t('uiAutomation.common.description')"
          />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.common.visibility')">
          <el-radio-group v-model="createForm.visibility">
            <el-radio value="all">{{ $t('uiAutomation.common.visibleAll') }}</el-radio>
            <el-radio value="private">{{ $t('uiAutomation.common.visibleSelf') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.suite.reuseBrowser')">
          <el-switch v-model="createForm.reuse_browser" />
          <span class="form-help-inline">{{ $t('uiAutomation.suite.reuseBrowserTip') }}</span>
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.suite.suiteItems')">
          <el-tabs v-model="suiteItemTab" style="width: 100%">
            <el-tab-pane
              :label="`${$t('uiAutomation.suite.testCases')} (${selectedTestCases.length})`"
              name="testCases"
            >
              <div class="test-case-selector">
                <div class="selector-panel">
                  <div class="panel-header">
                    <h4>{{ $t("uiAutomation.suite.availableCases") }}</h4>
                    <el-input
                      v-model="testCaseSearchText"
                      :placeholder="$t('uiAutomation.suite.searchCases')"
                      size="small"
                      clearable
                      style="width: 200px"
                    >
                      <template #prefix>
                        <el-icon><Search /></el-icon>
                      </template>
                    </el-input>
                  </div>
                  <div class="panel-content">
                    <el-table
                      :data="filteredAvailableTestCases"
                      height="300"
                      @row-click="handleTestCaseRowClick"
                      :row-class-name="getTestCaseRowClassName"
                    >
                      <el-table-column
                        prop="name"
                        :label="$t('uiAutomation.suite.caseName')"
                        min-width="150"
                        show-overflow-tooltip
                      />
                      <el-table-column
                        prop="priority"
                        :label="$t('uiAutomation.suite.priority')"
                        width="80"
                      >
                        <template #default="{ row }">
                          <el-tag size="small" :type="getPriorityTag(row.priority)">
                            {{ getPriorityText(row.priority) }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column
                        prop="status"
                        :label="$t('uiAutomation.common.status')"
                        width="80"
                      >
                        <template #default="{ row }">
                          <el-tag size="small" :type="getCaseStatusTag(row.status)">
                            {{ getCaseStatusText(row.status) }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column
                        :label="$t('uiAutomation.common.operation')"
                        width="80"
                      >
                        <template #default="{ row }">
                          <el-button
                            size="small"
                            text
                            @click.stop="addTestCase(row)"
                          >
                            <el-icon><ArrowRight /></el-icon>
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>

                <div class="selector-panel">
                  <div class="panel-header">
                    <h4>
                      {{ $t("uiAutomation.suite.selectedCases") }} ({{
                        selectedTestCases.length
                      }})
                    </h4>
                  </div>
                  <div class="panel-content">
                    <el-table :data="selectedTestCases" height="300">
                      <el-table-column
                        prop="name"
                        :label="$t('uiAutomation.suite.caseName')"
                        min-width="150"
                        show-overflow-tooltip
                      />
                      <el-table-column
                        prop="priority"
                        :label="$t('uiAutomation.suite.priority')"
                        width="80"
                      >
                        <template #default="{ row }">
                          <el-tag size="small" :type="getPriorityTag(row.priority)">
                            {{ getPriorityText(row.priority) }}
                          </el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column
                        :label="$t('uiAutomation.common.operation')"
                        width="120"
                      >
                        <template #default="{ $index }">
                          <el-button
                            size="small"
                            text
                            @click="moveUp($index)"
                            :disabled="$index === 0"
                          >
                            <el-icon><Top /></el-icon>
                          </el-button>
                          <el-button
                            size="small"
                            text
                            @click="moveDown($index)"
                            :disabled="$index === selectedTestCases.length - 1"
                          >
                            <el-icon><Bottom /></el-icon>
                          </el-button>
                          <el-button
                            size="small"
                            text
                            type="danger"
                            @click="removeTestCase($index)"
                          >
                            <el-icon><Delete /></el-icon>
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane
              :label="`${$t('uiAutomation.suite.scripts')} (${selectedScripts.length})`"
              name="scripts"
            >
              <div class="test-case-selector">
                <div class="selector-panel">
                  <div class="panel-header">
                    <h4>{{ $t("uiAutomation.suite.availableScripts") }}</h4>
                    <el-input
                      v-model="scriptSearchText"
                      :placeholder="$t('uiAutomation.suite.searchScripts')"
                      size="small"
                      clearable
                      style="width: 200px"
                    >
                      <template #prefix>
                        <el-icon><Search /></el-icon>
                      </template>
                    </el-input>
                  </div>
                  <div class="panel-content">
                    <el-table
                      :data="filteredAvailableScripts"
                      height="300"
                      @row-click="addScript"
                      :row-class-name="getScriptRowClassName"
                    >
                      <el-table-column
                        prop="name"
                        :label="$t('uiAutomation.suite.scriptName')"
                        min-width="150"
                        show-overflow-tooltip
                      />
                      <el-table-column
                        prop="framework"
                        :label="$t('uiAutomation.suite.framework')"
                        width="100"
                      >
                        <template #default="{ row }">
                          <el-tag size="small">{{ row.framework }}</el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column
                        prop="language"
                        :label="$t('uiAutomation.suite.language')"
                        width="80"
                      >
                        <template #default="{ row }">
                          {{ row.language }}
                        </template>
                      </el-table-column>
                      <el-table-column
                        :label="$t('uiAutomation.common.operation')"
                        width="80"
                      >
                        <template #default="{ row }">
                          <el-button
                            size="small"
                            text
                            @click.stop="addScript(row)"
                          >
                            <el-icon><ArrowRight /></el-icon>
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>

                <div class="selector-panel">
                  <div class="panel-header">
                    <h4>
                      {{ $t("uiAutomation.suite.selectedScripts") }} ({{
                        selectedScripts.length
                      }})
                    </h4>
                  </div>
                  <div class="panel-content">
                    <el-table :data="selectedScripts" height="300">
                      <el-table-column
                        prop="name"
                        :label="$t('uiAutomation.suite.scriptName')"
                        min-width="150"
                        show-overflow-tooltip
                      />
                      <el-table-column
                        prop="framework"
                        :label="$t('uiAutomation.suite.framework')"
                        width="100"
                      >
                        <template #default="{ row }">
                          <el-tag size="small">{{ row.framework }}</el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column
                        :label="$t('uiAutomation.common.operation')"
                        width="120"
                      >
                        <template #default="{ $index }">
                          <el-button
                            size="small"
                            text
                            @click="moveScriptUp($index)"
                            :disabled="$index === 0"
                          >
                            <el-icon><Top /></el-icon>
                          </el-button>
                          <el-button
                            size="small"
                            text
                            @click="moveScriptDown($index)"
                            :disabled="$index === selectedScripts.length - 1"
                          >
                            <el-icon><Bottom /></el-icon>
                          </el-button>
                          <el-button
                            size="small"
                            text
                            type="danger"
                            @click="removeScript($index)"
                          >
                            <el-icon><Delete /></el-icon>
                          </el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane
              :label="`${$t('uiAutomation.suite.executionOrder')} (${executionOrder.length})`"
              name="executionOrder"
            >
              <div class="execution-order-tip" v-if="executionOrder.length === 0">
                <el-empty :description="$t('uiAutomation.suite.executionOrderEmpty')" :image-size="60" />
              </div>
              <el-table v-else :data="executionOrder" height="350">
                <el-table-column type="index" width="50" :label="$t('uiAutomation.suite.orderNum')" />
                <el-table-column :label="$t('uiAutomation.suite.itemType')" width="80">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row._type === 'case' ? '' : 'success'">
                      {{ row._type === 'case' ? $t('uiAutomation.suite.typeCase') : $t('uiAutomation.suite.typeScript') }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="name" :label="$t('uiAutomation.common.name')" min-width="200" show-overflow-tooltip />
                <el-table-column :label="$t('uiAutomation.common.operation')" width="120">
                  <template #default="{ $index }">
                    <el-button size="small" text @click="moveOrderUp($index)" :disabled="$index === 0">
                      <el-icon><Top /></el-icon>
                    </el-button>
                    <el-button size="small" text @click="moveOrderDown($index)" :disabled="$index === executionOrder.length - 1">
                      <el-icon><Bottom /></el-icon>
                    </el-button>
                    <el-button size="small" text type="danger" @click="removeOrderItem($index)">
                      <el-icon><Delete /></el-icon>
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="cancelCreate">{{
            $t("uiAutomation.common.cancel")
          }}</el-button>
          <el-button type="primary" @click="handleCreate" :loading="saving">{{
            $t("uiAutomation.common.confirm")
          }}</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 运行配置对话框 -->
    <el-dialog
      v-model="showRunDialog"
      :title="$t('uiAutomation.suite.runConfig')"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="runConfig" label-width="120px">
        <el-form-item :label="$t('uiAutomation.suite.testEngine')">
          <el-select
            v-model="runConfig.engine"
            :placeholder="$t('uiAutomation.suite.testEngine')"
          >
            <el-option label="Playwright" value="playwright" />
            <el-option label="Selenium" value="selenium" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.suite.browser')">
          <el-select
            v-model="runConfig.browser"
            :placeholder="$t('uiAutomation.suite.browser')"
          >
            <el-option label="Chrome" value="chrome" />
            <el-option label="Firefox" value="firefox" />
            <el-option label="Safari" value="safari" />
            <el-option label="Edge" value="edge" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.suite.executionMode')">
          <el-radio-group v-model="runConfig.headless">
            <el-radio :label="false">{{
              $t("uiAutomation.suite.headedMode")
            }}</el-radio>
            <el-radio :label="true">{{
              $t("uiAutomation.suite.headlessMode")
            }}</el-radio>
          </el-radio-group>
          <div
            v-if="runConfig.executionMode === 'remote'"
            class="form-help-text"
          >
            {{ $t("uiAutomation.execution.remoteHeadlessHint") }}
          </div>
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.execution.executionMode')">
          <el-radio-group v-model="runConfig.executionMode" @change="onExecutionModeChange">
            <el-radio value="local">{{ $t('uiAutomation.execution.local') }}</el-radio>
            <el-radio value="remote">{{ $t('uiAutomation.execution.remote') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          v-if="runConfig.executionMode === 'remote'"
          :label="$t('uiAutomation.execution.remoteService')"
        >
          <el-select
            v-model="runConfig.remote_browser_service_id"
            :placeholder="$t('uiAutomation.execution.selectRemoteService')"
            style="width: 100%"
            @change="onRemoteServiceChange"
          >
            <el-option
              v-for="svc in remoteServices"
              :key="svc.id"
              :label="svc.name"
              :value="svc.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showRunDialog = false">{{
            $t("uiAutomation.common.cancel")
          }}</el-button>
          <el-button type="primary" @click="confirmRunSuite" :loading="running">
            {{ $t("uiAutomation.suite.startExecution") }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Plus,
  Search,
  Delete,
  ArrowRight,
  Top,
  Bottom,
} from "@element-plus/icons-vue";
import {
  getUiProjects,
  getTestSuites,
  createTestSuite,
  updateTestSuite,
  deleteTestSuite,
  getTestCases,
  getTestSuiteTestCases,
  addTestCaseToTestSuite,
  removeTestCaseFromTestSuite,
  updateTestCaseOrder,
  runTestSuite,
  getRemoteBrowserServices,
  getTestScripts,
  getTestSuiteScripts,
  addScriptToTestSuite,
  removeScriptFromTestSuite,
} from "@/api/ui_automation";
import { useI18n } from "vue-i18n";
import { localeDateTimeFormatter } from "@/utils/format";

const { t } = useI18n();

// 响应式数据
const projects = ref([]);
const projectId = ref("");
const suites = ref([]);
const loading = ref(false);
const searchText = ref("");
const total = ref(0);
const pagination = reactive({
  currentPage: 1,
  pageSize: 20,
});

// 对话框控制
const showCreateDialog = ref(false);
const showRunDialog = ref(false);
const isEditing = ref(false);
const currentSuiteId = ref(null);
const saving = ref(false);
const running = ref(false);

// 表单数据
const createForm = reactive({
  name: "",
  description: "",
  visibility: "all",
  reuse_browser: false,
});

// 表单验证规则 - 使用 computed 实现动态国际化
const formRules = computed(() => ({
  name: [
    {
      required: true,
      message: t("uiAutomation.suite.rules.nameRequired"),
      trigger: "blur",
    },
  ],
}));

// 测试用例相关
const availableTestCases = ref([]);
const selectedTestCases = ref([]);
const testCaseSearchText = ref("");

// 脚本相关
const availableScripts = ref([]);
const selectedScripts = ref([]);
const scriptSearchText = ref("");
const suiteItemTab = ref("testCases");

// 运行配置
const runConfig = reactive({
  engine: "playwright",
  browser: "chrome",
  headless: false,
  executionMode: "local",
  remote_browser_service_id: null,
});
const currentRunningSuite = ref(null);
const remoteServices = ref([]);

// 计算属性 - 过滤后的可用测试用例
const filteredAvailableTestCases = computed(() => {
  if (!testCaseSearchText.value) {
    return availableTestCases.value;
  }
  return availableTestCases.value.filter(
    (tc) =>
      tc.name.toLowerCase().includes(testCaseSearchText.value.toLowerCase()) ||
      (tc.description &&
        tc.description
          .toLowerCase()
          .includes(testCaseSearchText.value.toLowerCase())),
  );
});

const executionOrder = ref([]);

const syncExecutionOrder = () => {
  const caseItems = selectedTestCases.value.map((tc) => ({
    ...tc,
    _type: "case",
    _id: `case_${tc.id}`,
  }));
  const scriptItems = selectedScripts.value.map((s) => ({
    ...s,
    _type: "script",
    _id: `script_${s.id}`,
  }));

  const existingIds = new Set(executionOrder.value.map((item) => item._id));
  const newItems = [...caseItems, ...scriptItems].filter(
    (item) => !existingIds.has(item._id),
  );

  executionOrder.value = executionOrder.value
    .filter((item) => {
      if (item._type === "case")
        return selectedTestCases.value.some((tc) => tc.id === item.id);
      return selectedScripts.value.some((s) => s.id === item.id);
    })
    .concat(newItems);
};

watch([selectedTestCases, selectedScripts], syncExecutionOrder, { deep: true });

const moveOrderUp = (index) => {
  if (index > 0) {
    const list = executionOrder.value;
    const temp = list[index];
    list[index] = list[index - 1];
    list[index - 1] = temp;
  }
};

const moveOrderDown = (index) => {
  if (index < executionOrder.value.length - 1) {
    const list = executionOrder.value;
    const temp = list[index];
    list[index] = list[index + 1];
    list[index + 1] = temp;
  }
};

const removeOrderItem = (index) => {
  const item = executionOrder.value[index];
  executionOrder.value.splice(index, 1);
  if (item._type === "case") {
    const ci = selectedTestCases.value.findIndex((tc) => tc.id === item.id);
    if (ci >= 0) selectedTestCases.value.splice(ci, 1);
  } else {
    const si = selectedScripts.value.findIndex((s) => s.id === item.id);
    if (si >= 0) selectedScripts.value.splice(si, 1);
  }
};

const filteredAvailableScripts = computed(() => {
  if (!scriptSearchText.value) {
    return availableScripts.value;
  }
  const q = scriptSearchText.value.toLowerCase();
  return availableScripts.value.filter(
    (s) =>
      s.name.toLowerCase().includes(q) ||
      (s.description && s.description.toLowerCase().includes(q)),
  );
});

const loadProjects = async () => {
  try {
    const response = await getUiProjects({ page_size: 100 });
    projects.value = response.data.results || response.data;
  } catch (error) {
    console.error("获取项目列表失败:", error);
    ElMessage.error(t("uiAutomation.project.messages.loadFailed"));
  }
};

// 加载测试套件列表
const loadSuites = async () => {
  if (!projectId.value) {
    suites.value = [];
    total.value = 0;
    return;
  }

  loading.value = true;
  try {
    const response = await getTestSuites({
      project: projectId.value,
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      search: searchText.value,
    });

    if (response.data.results) {
      suites.value = response.data.results;
      total.value = response.data.count || 0;
    } else {
      suites.value = response.data;
      total.value = response.data.length;
    }
  } catch (error) {
    console.error("获取测试套件列表失败:", error);
    ElMessage.error(t("uiAutomation.suite.messages.loadFailed"));
  } finally {
    loading.value = false;
  }
};

// 加载可用测试用例
const loadAvailableTestCases = async () => {
  if (!projectId.value) return;

  try {
    const response = await getTestCases({
      project: projectId.value,
      page_size: 1000, // 加载所有用例
    });
    availableTestCases.value = response.data.results || response.data;
  } catch (error) {
    console.error("获取测试用例列表失败:", error);
    ElMessage.error(t("uiAutomation.suite.messages.loadCasesFailed"));
  }
};

const loadAvailableScripts = async () => {
  if (!projectId.value) return;
  try {
    const response = await getTestScripts({
      project: projectId.value,
      page_size: 1000,
    });
    availableScripts.value = response.data.results || response.data;
  } catch (error) {
    console.error("Failed to load scripts:", error);
  }
};

const onProjectChange = async () => {
  pagination.currentPage = 1;
  await loadSuites();
};

// 搜索处理
const handleSearch = async () => {
  pagination.currentPage = 1;
  await loadSuites();
};

// 分页处理
const handleSizeChange = async () => {
  pagination.currentPage = 1;
  await loadSuites();
};

const handleCurrentChange = async () => {
  await loadSuites();
};

// 新增套件
const handleCreate = async () => {
  if (!createForm.name) {
    ElMessage.warning(t("uiAutomation.suite.messages.inputName"));
    return;
  }

  if (!projectId.value) {
    ElMessage.warning(t("uiAutomation.suite.messages.selectProject"));
    return;
  }

  saving.value = true;
  try {
    const suiteData = {
      project: projectId.value,
      name: createForm.name,
      description: createForm.description,
      visibility: createForm.visibility,
      reuse_browser: createForm.reuse_browser,
    };

    let suiteId;
    if (isEditing.value) {
      // 更新套件
      await updateTestSuite(currentSuiteId.value, suiteData);
      suiteId = currentSuiteId.value;
      ElMessage.success(t("uiAutomation.suite.messages.updateSuccess"));
    } else {
      // 创建套件
      const response = await createTestSuite(suiteData);
      suiteId = response.data.id;
      ElMessage.success(t("uiAutomation.suite.messages.createSuccess"));
    }

    // 清除旧关联
    if (isEditing.value) {
      const existingTestCases = await getTestSuiteTestCases(suiteId);
      for (const tc of existingTestCases.data) {
        await removeTestCaseFromTestSuite(suiteId, tc.test_case.id);
      }
      const existingScripts = await getTestSuiteScripts(suiteId);
      for (const ss of existingScripts.data) {
        await removeScriptFromTestSuite(suiteId, ss.test_script.id);
      }
    }

    // 按执行顺序保存关联（统一 order 序号）
    syncExecutionOrder();
    for (let i = 0; i < executionOrder.value.length; i++) {
      const item = executionOrder.value[i];
      if (item._type === "case") {
        await addTestCaseToTestSuite(suiteId, {
          test_case_id: item.id,
          order: i,
        });
      } else {
        await addScriptToTestSuite(suiteId, {
          test_script_id: item.id,
          order: i,
        });
      }
    }

    showCreateDialog.value = false;
    await loadSuites();
    resetForm();
  } catch (error) {
    console.error("保存测试套件失败:", error);
    ElMessage.error(t("uiAutomation.suite.messages.saveFailed"));
  } finally {
    saving.value = false;
  }
};

// 编辑套件
const editSuite = async (id) => {
  try {
    // 加载套件详情
    const suites_data = suites.value.find((s) => s.id === id);
    if (!suites_data) return;

    currentSuiteId.value = id;
    isEditing.value = true;
    createForm.name = suites_data.name;
    createForm.description = suites_data.description;
    createForm.visibility = suites_data.visibility || "all";
    createForm.reuse_browser = suites_data.reuse_browser || false;

    // 加载已选测试用例和脚本，按统一 order 合并
    const [tcResponse, scriptResponse] = await Promise.all([
      getTestSuiteTestCases(id),
      getTestSuiteScripts(id),
    ]);

    const caseItems = (tcResponse.data || []).map((item) => ({
      ...item.test_case,
      _type: "case",
      _id: `case_${item.test_case.id}`,
      _order: item.order,
    }));
    const scriptItems = (scriptResponse.data || []).map((item) => ({
      ...item.test_script,
      _type: "script",
      _id: `script_${item.test_script.id}`,
      _order: item.order,
    }));

    // 统一按 order 排序
    const allItems = [...caseItems, ...scriptItems].sort(
      (a, b) => a._order - b._order,
    );
    executionOrder.value = allItems;

    selectedTestCases.value = caseItems
      .sort((a, b) => a._order - b._order)
      .map(({ _type, _id, _order, ...rest }) => rest);
    selectedScripts.value = scriptItems
      .sort((a, b) => a._order - b._order)
      .map(({ _type, _id, _order, ...rest }) => rest);

    // 加载可用测试用例和脚本
    await Promise.all([loadAvailableTestCases(), loadAvailableScripts()]);

    showCreateDialog.value = true;
  } catch (error) {
    console.error("加载套件详情失败:", error);
    ElMessage.error(t("uiAutomation.suite.messages.loadDetailFailed"));
  }
};

// 删除套件
const deleteSuite = async (id) => {
  try {
    await ElMessageBox.confirm(
      t("uiAutomation.suite.messages.deleteConfirm"),
      t("uiAutomation.messages.confirm.tip"),
      {
        confirmButtonText: t("uiAutomation.common.confirm"),
        cancelButtonText: t("uiAutomation.common.cancel"),
        type: "warning",
      },
    );

    await deleteTestSuite(id);
    ElMessage.success(t("uiAutomation.suite.messages.deleteSuccess"));
    await loadSuites();
  } catch (error) {
    if (error !== "cancel") {
      console.error("删除测试套件失败:", error);
      ElMessage.error(t("uiAutomation.suite.messages.deleteFailed"));
    }
  }
};

// 运行套件
const runSuite = (suite) => {
  const totalItems = (suite.test_case_count || 0) + (suite.script_count || 0);
  if (totalItems === 0) {
    ElMessage.warning(t("uiAutomation.suite.messages.noCases"));
    return;
  }

  currentRunningSuite.value = suite;
  showRunDialog.value = true;
};

// 执行方式切换（本地/远程）
function onExecutionModeChange(mode) {
  if (mode === "local") {
    runConfig.remote_browser_service_id = null;
  } else {
    fetchRemoteServices();
  }
}

// 加载可用的远程浏览器服务
async function fetchRemoteServices() {
  try {
    const res = await getRemoteBrowserServices({
      project: projectId.value,
      is_active: true,
      online: true,
    });
    const list = res.data?.results || res.data || [];
    // 前端再兜底过滤一次，不管后端筛选是否生效，都不展示已停用/已离线的服务。
    // is_online 是后端新加的字段，用 !== false（而不是 === true）兼容后端还没
    // 部署这次改动的情况，不会把老数据全部误判成离线
    remoteServices.value = list.filter(
      (s) => s.is_active !== false && s.is_online !== false,
    );
  } catch (e) {
    console.error("Failed to fetch remote services:", e);
  }
}

// 选择远程服务后自动锁定对应的执行引擎
function onRemoteServiceChange(serviceId) {
  const svc = remoteServices.value.find((s) => s.id === serviceId);
  if (!svc) return;
  if (["selenium_grid", "browserstack", "saucelabs"].includes(svc.service_type)) {
    runConfig.engine = "selenium";
  } else if (["playwright_remote", "playwright_cdp"].includes(svc.service_type)) {
    runConfig.engine = "playwright";
  }
}

// 确认运行套件
const confirmRunSuite = async () => {
  running.value = true;
  try {
    const requestData = {
      use_ai: false,
      engine: runConfig.engine,
      browser: runConfig.browser,
      headless: runConfig.headless,
      remote_browser_service_id:
        runConfig.executionMode === "remote"
          ? runConfig.remote_browser_service_id
          : null,
    };

    const response = await runTestSuite(
      currentRunningSuite.value.id,
      requestData,
    );

    ElMessage.success(t("uiAutomation.suite.messages.startSuccess"));
    showRunDialog.value = false;

    // 立即刷新一次以显示"运行中"状态
    await loadSuites();

    // 开始轮询检查执行状态
    pollSuiteStatus(currentRunningSuite.value.id);
  } catch (error) {
    console.error("执行测试套件失败:", error);
    // 如果后端返回了错误消息，显示具体错误
    const errorMsg =
      error.response?.data?.error ||
      t("uiAutomation.suite.messages.executeFailed");
    ElMessage.error(errorMsg);
  } finally {
    running.value = false;
  }
};

// 轮询检查套件执行状态
const pollSuiteStatus = (suiteId) => {
  let pollCount = 0;
  const maxPolls = 120; // 最多轮询2分钟（每秒一次）

  const pollInterval = setInterval(async () => {
    pollCount++;

    try {
      // 重新加载套件列表
      await loadSuites();

      // 查找当前套件的状态
      const currentSuite = suites.value.find((s) => s.id === suiteId);

      if (currentSuite && currentSuite.execution_status !== "running") {
        // 执行完成，停止轮询
        clearInterval(pollInterval);

        // 根据状态显示消息
        if (currentSuite.execution_status === "passed") {
          ElMessage.success(
            `${t("uiAutomation.suite.messages.executionComplete")}: ${t("uiAutomation.suite.messages.allPassed")} (${currentSuite.passed_count}/${currentSuite.passed_count + currentSuite.failed_count})`,
          );
        } else if (currentSuite.execution_status === "failed") {
          ElMessage.warning(
            `${t("uiAutomation.suite.messages.executionComplete")}: ${t("uiAutomation.suite.messages.partialFailed")} (${t("uiAutomation.suite.messages.passed")}: ${currentSuite.passed_count}, ${t("uiAutomation.status.failed")}: ${currentSuite.failed_count})`,
          );
        }
      }

      // 超过最大轮询次数，停止轮询
      if (pollCount >= maxPolls) {
        clearInterval(pollInterval);
        ElMessage.info(t("uiAutomation.suite.messages.longExecution"));
      }
    } catch (error) {
      console.error("轮询套件状态失败:", error);
      // 发生错误时停止轮询
      clearInterval(pollInterval);
    }
  }, 3000); // 每3秒轮询一次
};

// 测试用例管理方法
const handleTestCaseRowClick = (row) => {
  // 双击添加测试用例
  addTestCase(row);
};

const getTestCaseRowClassName = ({ row }) => {
  // 如果已选中，添加特殊样式
  return selectedTestCases.value.some((tc) => tc.id === row.id)
    ? "selected-row"
    : "";
};

const addTestCase = (testCase) => {
  // 检查是否已存在
  if (selectedTestCases.value.some((tc) => tc.id === testCase.id)) {
    ElMessage.warning(t("uiAutomation.suite.messages.caseAdded"));
    return;
  }
  selectedTestCases.value.push({ ...testCase });
};

const removeTestCase = (index) => {
  selectedTestCases.value.splice(index, 1);
};

const moveUp = (index) => {
  if (index > 0) {
    const temp = selectedTestCases.value[index];
    selectedTestCases.value[index] = selectedTestCases.value[index - 1];
    selectedTestCases.value[index - 1] = temp;
  }
};

const moveDown = (index) => {
  if (index < selectedTestCases.value.length - 1) {
    const temp = selectedTestCases.value[index];
    selectedTestCases.value[index] = selectedTestCases.value[index + 1];
    selectedTestCases.value[index + 1] = temp;
  }
};

const addScript = (script) => {
  if (selectedScripts.value.some((s) => s.id === script.id)) {
    ElMessage.warning(t("uiAutomation.suite.messages.scriptAdded"));
    return;
  }
  selectedScripts.value.push({ ...script });
};

const removeScript = (index) => {
  selectedScripts.value.splice(index, 1);
};

const moveScriptUp = (index) => {
  if (index > 0) {
    const temp = selectedScripts.value[index];
    selectedScripts.value[index] = selectedScripts.value[index - 1];
    selectedScripts.value[index - 1] = temp;
  }
};

const moveScriptDown = (index) => {
  if (index < selectedScripts.value.length - 1) {
    const temp = selectedScripts.value[index];
    selectedScripts.value[index] = selectedScripts.value[index + 1];
    selectedScripts.value[index + 1] = temp;
  }
};

const getScriptRowClassName = ({ row }) => {
  return selectedScripts.value.some((s) => s.id === row.id)
    ? "selected-row"
    : "";
};

const resetForm = () => {
  createForm.name = "";
  createForm.description = "";
  createForm.visibility = "all";
  createForm.reuse_browser = false;
  selectedTestCases.value = [];
  testCaseSearchText.value = "";
  selectedScripts.value = [];
  scriptSearchText.value = "";
  executionOrder.value = [];
  suiteItemTab.value = "testCases";
  isEditing.value = false;
  currentSuiteId.value = null;
};

// 取消创建
const cancelCreate = () => {
  showCreateDialog.value = false;
  resetForm();
};

// 新增套件按钮点击
const handleCreateButtonClick = async () => {
  resetForm();
  await loadAvailableTestCases();
  showCreateDialog.value = true;
};


const getExecutionStatusTag = (status) => {
  const statusMap = {
    not_run: "info",
    passed: "success",
    failed: "danger",
    running: "warning",
  };
  return statusMap[status] || "info";
};

const getExecutionStatusText = (status) => {
  const statusKey = {
    not_run: "notRun",
    passed: "passed",
    failed: "failed",
    running: "running",
  }[status];
  return statusKey
    ? t(`uiAutomation.status.${statusKey}`)
    : t("uiAutomation.status.unknown");
};

const getPriorityTag = (priority) => {
  const priorityMap = {
    high: "danger",
    medium: "warning",
    low: "info",
  };
  return priorityMap[priority] || "info";
};

const getPriorityText = (priority) => {
  const priorityKey = {
    high: "high",
    medium: "medium",
    low: "low",
  }[priority];
  return priorityKey
    ? t(`uiAutomation.priority.${priorityKey}`)
    : t("uiAutomation.status.unknown");
};

const getCaseStatusTag = (status) => {
  const statusMap = {
    draft: "info",
    ready: "primary",
    running: "warning",
    passed: "success",
    failed: "danger",
  };
  return statusMap[status] || "info";
};

const getCaseStatusText = (status) => {
  const statusKey = {
    draft: "draft",
    ready: "ready",
    running: "running",
    passed: "passed",
    failed: "failed",
  }[status];
  return statusKey
    ? t(`uiAutomation.status.${statusKey}`)
    : t("uiAutomation.status.unknown");
};

// 监听新增套件按钮
const originalShowCreateDialog = showCreateDialog;
onMounted(async () => {
  await loadProjects();
  if (projects.value.length > 0) {
    projectId.value = projects.value[0].id;
    await loadSuites();
  }
});

// 监听对话框打开事件
const openCreateDialog = async () => {
  if (!isEditing.value) {
    await Promise.all([loadAvailableTestCases(), loadAvailableScripts()]);
  }
};

const handleNewSuite = async () => {
  resetForm();
  await Promise.all([loadAvailableTestCases(), loadAvailableScripts()]);
  showCreateDialog.value = true;
};
</script>

<style scoped lang="scss">
.page-container {
  padding: 20px;
  background: #f5f5f5;
  min-height: 100vh;
}

.form-help-text {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
  line-height: 1.4;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  background: white;
  padding: 20px;
  border-radius: 4px;
}

.page-title {
  margin: 0;
  font-size: 24px;
}

.card-container {
  background: white;
  padding: 20px;
  border-radius: 4px;
}

.filter-bar {
  margin-bottom: 20px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

// 测试用例选择器样式
.test-case-selector {
  display: flex;
  gap: 20px;
  width: 100%;
}

.selector-panel {
  flex: 1;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.panel-header {
  background: #f5f7fa;
  padding: 12px 15px;
  border-bottom: 1px solid #dcdfe6;
  display: flex;
  justify-content: space-between;
  align-items: center;

  h4 {
    margin: 0;
    font-size: 14px;
    color: #303133;
  }
}

.panel-content {
  padding: 10px;
}

:deep(.selected-row) {
  background-color: #f0f9ff !important;
}

:deep(.el-table__row) {
  cursor: pointer;

  &:hover {
    background-color: #f5f7fa;
  }
}

.mode-description {
  margin-top: 8px;

  .description-text {
    font-size: 12px;
    color: #909399;
    line-height: 1.5;
  }
}

.form-help-inline {
  margin-left: 10px;
  font-size: 12px;
  color: #909399;
}
</style>
