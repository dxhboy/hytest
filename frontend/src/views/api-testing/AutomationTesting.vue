<template>
  <div class="automation-testing">
    <div class="header">
      <h3>{{ $t("apiTesting.automation.title") }}</h3>
      <el-button type="primary" @click="showCreateSuiteDialog = true">
        <el-icon><Plus /></el-icon>
        {{ $t("apiTesting.automation.createSuite") }}
      </el-button>
    </div>

    <div class="content-layout">
      <!-- 左侧项目选择和测试套件列表 -->
      <div class="sidebar">
        <div class="project-selector">
          <el-select
            v-model="selectedProject"
            :placeholder="$t('apiTesting.common.selectProject')"
            @change="onProjectChange"
            style="width: 100%"
          >
            <el-option
              v-for="project in httpProjects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </div>

        <div class="suite-list">
          <div class="list-header">
            <span>{{ $t("apiTesting.automation.testSuites") }}</span>
            <el-button size="small" text @click="loadTestSuites">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>

          <el-scrollbar height="400px">
            <div
              v-for="suite in testSuites"
              :key="suite.id"
              class="suite-item"
              :class="{ active: selectedSuite?.id === suite.id }"
              @click="selectSuite(suite)"
            >
              <div class="suite-info">
                <div class="suite-name">{{ suite.name }}</div>
                <div class="suite-meta">
                  {{
                    $t("apiTesting.automation.requestCount", {
                      n: suite.suite_requests?.length || 0,
                    })
                  }}
                </div>
              </div>
              <el-dropdown @command="handleSuiteAction" trigger="click">
                <el-button size="small" text>
                  <el-icon><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item :command="{ action: 'run', suite }">{{
                      $t("apiTesting.automation.run")
                    }}</el-dropdown-item>
                    <el-dropdown-item :command="{ action: 'edit', suite }">{{
                      $t("apiTesting.common.edit")
                    }}</el-dropdown-item>
                    <el-dropdown-item
                      :command="{ action: 'duplicate', suite }"
                      >{{ $t("apiTesting.common.copy") }}</el-dropdown-item
                    >
                    <el-dropdown-item
                      :command="{ action: 'delete', suite }"
                      divided
                      >{{ $t("apiTesting.common.delete") }}</el-dropdown-item
                    >
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </el-scrollbar>
        </div>
      </div>

      <!-- 右侧测试套件详情 -->
      <div class="main-content">
        <div v-if="!selectedSuite" class="empty-state">
          <el-empty
            :description="$t('apiTesting.automation.selectSuiteHint')"
          />
        </div>

        <div v-else class="suite-detail">
          <!-- 套件信息 -->
          <div class="suite-header">
            <div class="suite-title">
              <h4>{{ selectedSuite.name }}</h4>
              <div class="suite-actions">
                <el-button
                  type="success"
                  @click="runTestSuite(selectedSuite)"
                  :loading="running"
                >
                  <el-icon><VideoPlay /></el-icon>
                  {{ $t("apiTesting.automation.runTest") }}
                </el-button>
                <el-button @click="editSuite(selectedSuite)">
                  <el-icon><Edit /></el-icon>
                  {{ $t("apiTesting.common.edit") }}
                </el-button>
              </div>
            </div>
            <div class="suite-description">
              {{
                selectedSuite.description ||
                $t("apiTesting.automation.noDescription")
              }}
            </div>
            <div class="suite-meta">
              <el-tag size="small">{{
                getEnvironmentName(selectedSuite.environment)
              }}</el-tag>
              <span class="meta-text"
                >{{ $t("apiTesting.automation.creator")
                }}{{ selectedSuite.created_by?.username }}</span
              >
              <span class="meta-text"
                >{{ $t("apiTesting.automation.createTime")
                }}{{ formatDate(selectedSuite.created_at) }}</span
              >
            </div>
          </div>

          <!-- 请求列表 -->
          <div class="requests-section">
            <div class="section-header">
              <h5>{{ $t("apiTesting.automation.testRequests") }}</h5>
              <el-button size="small" @click="showAddRequest">
                <el-icon><Plus /></el-icon>
                {{ $t("apiTesting.automation.addRequest") }}
              </el-button>
            </div>

            <div class="drag-table">
              <div class="drag-table-header">
                <div class="drag-col drag-col-handle"></div>
                <div class="drag-col drag-col-index">#</div>
                <div class="drag-col drag-col-name">
                  {{ $t("apiTesting.automation.requestName") }}
                </div>
                <div class="drag-col drag-col-method">
                  {{ $t("apiTesting.automation.method") }}
                </div>
                <div class="drag-col drag-col-url">URL</div>
                <div class="drag-col drag-col-enabled">
                  {{ $t("apiTesting.automation.enabled") }}
                </div>
                <div class="drag-col drag-col-assertions">
                  {{ $t("apiTesting.automation.assertions") }}
                </div>
                <div class="drag-col drag-col-actions">
                  {{ $t("apiTesting.common.operation") }}
                </div>
              </div>
              <draggable
                v-model="sortableRequests"
                item-key="id"
                handle=".drag-handle"
                @end="onDragEnd"
                :animation="200"
              >
                <template #item="{ element, index }">
                  <div
                    class="drag-table-row"
                    :class="{ disabled: !element.enabled }"
                  >
                    <div class="drag-col drag-col-handle">
                      <el-icon class="drag-handle" v-loading="savingOrder"
                        ><Rank
                      /></el-icon>
                    </div>
                    <div class="drag-col drag-col-index">{{ index + 1 }}</div>
                    <div
                      class="drag-col drag-col-name"
                      :title="element.request.name"
                    >
                      {{ element.request.name }}
                    </div>
                    <div class="drag-col drag-col-method">
                      <el-tag
                        :type="getMethodType(element.request.method)"
                        size="small"
                      >
                        {{ element.request.method }}
                      </el-tag>
                    </div>
                    <div
                      class="drag-col drag-col-url"
                      :title="element.request.url"
                    >
                      {{ element.request.url }}
                    </div>
                    <div class="drag-col drag-col-enabled">
                      <el-switch
                        v-model="element.enabled"
                        @change="updateRequestEnabled(element)"
                      />
                    </div>
                    <div class="drag-col drag-col-assertions">
                      {{
                        $t("apiTesting.automation.assertionCount", {
                          n: element.assertions?.length || 0,
                        })
                      }}
                    </div>
                    <div class="drag-col drag-col-actions">
                      <el-button
                        link
                        type="primary"
                        size="small"
                        @click="editAssertions(element)"
                      >
                        {{ $t("apiTesting.automation.editAssertions") }}
                      </el-button>
                      <el-button
                        link
                        type="danger"
                        size="small"
                        @click="removeRequest(element)"
                      >
                        {{ $t("apiTesting.automation.remove") }}
                      </el-button>
                    </div>
                  </div>
                </template>
              </draggable>
              <div
                v-if="sortableRequests.length === 0"
                class="drag-table-empty"
              >
                <el-empty
                  :description="
                    $t('apiTesting.automation.noRequests') || '暂无请求'
                  "
                  :image-size="60"
                />
              </div>
            </div>
          </div>

          <!-- 执行历史 -->
          <div class="executions-section">
            <div class="section-header">
              <h5>{{ $t("apiTesting.automation.executionHistory") }}</h5>
              <el-button size="small" @click="loadExecutions">
                <el-icon><Refresh /></el-icon>
                {{ $t("apiTesting.automation.refresh") }}
              </el-button>
            </div>

            <el-table :data="executions" v-loading="executionsLoading">
              <el-table-column
                prop="status"
                :label="$t('apiTesting.common.status')"
                width="100"
              >
                <template #default="scope">
                  <el-tag :type="getStatusType(scope.row.status)">
                    {{ getStatusText(scope.row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="total_requests"
                :label="$t('apiTesting.automation.totalRequests')"
                width="100"
              />
              <el-table-column
                prop="passed_requests"
                :label="$t('apiTesting.automation.passedCount')"
                width="100"
              >
                <template #default="scope">
                  <span style="color: #67c23a">{{
                    scope.row.passed_requests
                  }}</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="failed_requests"
                :label="$t('apiTesting.automation.failedCount')"
                width="100"
              >
                <template #default="scope">
                  <span style="color: #f56c6c">{{
                    scope.row.failed_requests
                  }}</span>
                </template>
              </el-table-column>
              <el-table-column
                :label="$t('apiTesting.automation.averageTime')"
                width="120"
              >
                <template #default="scope">
                  {{ getAverageExecutionTime(scope.row) }}
                </template>
              </el-table-column>
              <el-table-column
                prop="executed_by.username"
                :label="$t('apiTesting.automation.executor')"
                width="120"
              />
              <el-table-column
                prop="created_at"
                :label="$t('apiTesting.automation.executionTime')"
                width="160"
              >
                <template #default="scope">
                  {{ formatDate(scope.row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column
                :label="$t('apiTesting.common.operation')"
                width="120"
              >
                <template #default="scope">
                  <el-button
                    link
                    type="primary"
                    @click="viewExecutionDetail(scope.row)"
                    size="small"
                  >
                    {{ $t("apiTesting.automation.viewDetails") }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑测试套件对话框 -->
    <el-dialog
      v-model="showCreateSuiteDialog"
      :title="
        editingSuite
          ? $t('apiTesting.automation.editSuite')
          : $t('apiTesting.automation.createSuite')
      "
      width="600px"
      :close-on-click-modal="false"
      @close="resetSuiteForm"
    >
      <el-form
        ref="suiteFormRef"
        :model="suiteForm"
        :rules="suiteRules"
        label-width="100px"
      >
        <el-form-item
          :label="$t('apiTesting.automation.suiteName')"
          prop="name"
        >
          <el-input
            v-model="suiteForm.name"
            :placeholder="$t('apiTesting.automation.inputSuiteName')"
          />
        </el-form-item>

        <el-form-item
          :label="$t('apiTesting.automation.suiteDescription')"
          prop="description"
        >
          <el-input
            v-model="suiteForm.description"
            type="textarea"
            :rows="3"
            :placeholder="$t('apiTesting.automation.inputSuiteDescription')"
          />
        </el-form-item>

        <el-form-item
          :label="$t('apiTesting.automation.belongProject')"
          prop="project"
        >
          <el-select
            v-model="suiteForm.project"
            :placeholder="$t('apiTesting.automation.selectProject')"
          >
            <el-option
              v-for="project in httpProjects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item
          :label="$t('apiTesting.automation.executionEnvironment')"
          prop="environment"
        >
          <el-select
            v-model="suiteForm.environment"
            :placeholder="$t('apiTesting.automation.selectEnvironment')"
            clearable
          >
            <el-option
              v-for="env in environments"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('apiTesting.common.visibility')">
          <el-radio-group v-model="suiteForm.visibility">
            <el-radio value="all">{{ $t('apiTesting.common.visibleAll') }}</el-radio>
            <el-radio value="private">{{ $t('apiTesting.common.visibleSelf') }}</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateSuiteDialog = false">{{
          $t("apiTesting.common.cancel")
        }}</el-button>
        <el-button
          type="primary"
          @click="submitSuiteForm"
          :loading="submittingSuite"
        >
          {{
            editingSuite
              ? $t("apiTesting.common.update")
              : $t("apiTesting.common.create")
          }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 添加请求对话框 -->
    <el-dialog
      v-model="showAddRequestDialog"
      :title="$t('apiTesting.automation.addRequestToSuite')"
      width="800px"
      :close-on-click-modal="false"
    >
      <div class="add-request-content">
        <div class="request-selector">
          <el-tree
            ref="requestTreeRef"
            :data="requestTree"
            :props="requestTreeProps"
            show-checkbox
            node-key="id"
            :check-on-click-node="false"
            @check="onRequestCheck"
          >
            <template #default="{ data }">
              <div class="request-tree-node">
                <el-icon v-if="data.type === 'collection'">
                  <Folder />
                </el-icon>
                <el-icon v-else>
                  <Document />
                </el-icon>
                <span>{{ data.name }}</span>
                <span
                  v-if="data.type === 'request'"
                  class="method-tag"
                  :class="data.method?.toLowerCase()"
                >
                  {{ data.method }}
                </span>
              </div>
            </template>
          </el-tree>
        </div>
      </div>

      <template #footer>
        <el-button @click="showAddRequestDialog = false">{{
          $t("apiTesting.common.cancel")
        }}</el-button>
        <el-button
          type="primary"
          @click="addSelectedRequests"
          :loading="addingRequests"
        >
          {{ $t("apiTesting.automation.addSelectedRequests") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 断言编辑对话框 -->
    <el-dialog
      v-model="showAssertionDialog"
      :title="$t('apiTesting.automation.editAssertions')"
      width="700px"
      :close-on-click-modal="false"
      @close="showAssertionDialog = false"
    >
      <div class="assertions-editor">
        <div class="assertions-header">
          <el-button type="primary" size="small" @click="addAssertion">
            <el-icon><Plus /></el-icon>
            {{ $t("apiTesting.automation.addAssertion") }}
          </el-button>
        </div>

        <div v-if="editingAssertions.length === 0" class="empty-assertions">
          <el-empty :description="$t('apiTesting.automation.noAssertions')" />
        </div>

        <div v-else class="assertions-list">
          <div
            v-for="(assertion, index) in editingAssertions"
            :key="index"
            class="assertion-item"
          >
            <div class="assertion-row">
              <el-select
                v-model="assertion.type"
                size="small"
                style="width: 120px"
                @change="onAssertionTypeChange(assertion)"
              >
                <el-option
                  v-for="type in assertionTypes"
                  :key="type.value"
                  :label="type.label"
                  :value="type.value"
                />
              </el-select>

              <!-- 状态码断言 -->
              <template v-if="assertion.type === 'status_code'">
                <el-select
                  v-model="assertion.operator"
                  size="small"
                  style="width: 100px"
                >
                  <el-option label="等于" value="eq" />
                  <el-option label="不等于" value="ne" />
                  <el-option label="大于" value="gt" />
                  <el-option label="大于等于" value="gte" />
                  <el-option label="小于" value="lt" />
                  <el-option label="小于等于" value="lte" />
                </el-select>
                <el-input-number
                  v-model="assertion.expected"
                  size="small"
                  style="width: 120px"
                  :min="100"
                  :max="599"
                />
              </template>

              <!-- JSON路径断言 -->
              <template v-else-if="assertion.type === 'json_path'">
                <el-input
                  v-model="assertion.path"
                  size="small"
                  placeholder="JSON路径，如：data.user.name"
                  style="width: 150px"
                />
                <el-select
                  v-model="assertion.operator"
                  size="small"
                  style="width: 100px"
                >
                  <el-option label="等于" value="eq" />
                  <el-option label="包含" value="contains" />
                  <el-option label="存在" value="exists" />
                  <el-option label="类型为" value="type" />
                </el-select>
                <el-input
                  v-model="assertion.expected"
                  size="small"
                  placeholder="期望值"
                  style="width: 150px"
                />
              </template>

              <!-- 响应时间断言 -->
              <template v-else-if="assertion.type === 'response_time'">
                <el-select
                  v-model="assertion.operator"
                  size="small"
                  style="width: 100px"
                >
                  <el-option label="小于" value="lt" />
                  <el-option label="小于等于" value="lte" />
                </el-select>
                <el-input-number
                  v-model="assertion.value"
                  size="small"
                  style="width: 120px"
                  :min="0"
                  :step="100"
                />
                <span style="margin-left: 8px">ms</span>
              </template>

              <!-- 响应头断言 -->
              <template v-else-if="assertion.type === 'header'">
                <el-input
                  v-model="assertion.key"
                  size="small"
                  placeholder="响应头字段，如：Content-Type"
                  style="width: 120px"
                />
                <el-select
                  v-model="assertion.operator"
                  size="small"
                  style="width: 100px"
                >
                  <el-option label="存在" value="exists" />
                  <el-option label="等于" value="eq" />
                  <el-option label="包含" value="contains" />
                </el-select>
                <el-input
                  v-model="assertion.value"
                  size="small"
                  placeholder="期望值"
                  style="width: 150px"
                />
              </template>

              <!-- 响应体包含断言 -->
              <template v-else-if="assertion.type === 'body_contains'">
                <el-input
                  v-model="assertion.value"
                  size="small"
                  placeholder="期望包含的文本"
                  style="width: 250px"
                />
              </template>

              <el-switch
                v-model="assertion.enabled"
                size="small"
                style="margin: 0 8px"
                :active-text="$t('apiTesting.common.enable')"
                :inactive-text="$t('apiTesting.common.disable')"
              />

              <el-button
                type="danger"
                size="small"
                @click="removeAssertion(index)"
                :icon="Delete"
                circle
              />
            </div>

            <!-- 错误消息（用于显示断言失败时的自定义消息） -->
            <div
              class="assertion-message"
              v-if="assertion.message !== undefined"
            >
              <el-input
                v-model="assertion.message"
                size="small"
                placeholder="失败时的自定义错误消息（可选）"
              />
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showAssertionDialog = false">{{
          $t("apiTesting.common.cancel")
        }}</el-button>
        <el-button
          type="primary"
          @click="saveAssertions"
          :loading="submittingAssertions"
        >
          {{ $t("apiTesting.common.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 执行结果对话框 -->
    <el-dialog
      v-model="showExecutionDialog"
      :title="$t('apiTesting.automation.testExecutionResult')"
      width="80%"
      :top="'5vh'"
    >
      <div v-if="currentExecution" class="execution-detail">
        <div class="execution-summary">
          <el-row :gutter="20">
            <el-col :span="6">
              <el-statistic
                :title="$t('apiTesting.automation.totalRequests')"
                :value="currentExecution.total_requests"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                :title="$t('apiTesting.automation.passedCount')"
                :value="currentExecution.passed_requests"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                :title="$t('apiTesting.automation.failedCount')"
                :value="currentExecution.failed_requests"
              />
            </el-col>
            <el-col :span="6">
              <el-statistic
                :title="$t('apiTesting.automation.passRate')"
                :value="getPassRate(currentExecution)"
                suffix="%"
              />
            </el-col>
          </el-row>
        </div>

        <div class="execution-results">
          <h4>{{ $t("apiTesting.automation.detailedResults") }}</h4>
          <el-table :data="formatExecutionResults(currentExecution.results)">
            <el-table-column
              prop="name"
              :label="$t('apiTesting.automation.requestName')"
              min-width="200"
            />
            <el-table-column
              prop="method"
              :label="$t('apiTesting.automation.method')"
              width="80"
            >
              <template #default="scope">
                <el-tag :type="getMethodType(scope.row.method)" size="small">
                  {{ scope.row.method }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="status"
              :label="$t('apiTesting.automation.result')"
              width="100"
            >
              <template #default="scope">
                <el-tag
                  :type="scope.row.passed ? 'success' : 'danger'"
                  size="small"
                >
                  {{
                    scope.row.passed
                      ? $t("apiTesting.automation.status.passed")
                      : $t("apiTesting.automation.status.failed")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="status_code"
              :label="$t('apiTesting.automation.statusCode')"
              width="100"
            />
            <el-table-column
              prop="response_time"
              :label="$t('apiTesting.automation.responseTime')"
              width="120"
            >
              <template #default="scope">
                {{ scope.row.response_time?.toFixed(0) }}ms
              </template>
            </el-table-column>
            <el-table-column
              prop="error"
              :label="$t('apiTesting.automation.errorMessage')"
              min-width="200"
              show-overflow-tooltip
            />

            <!-- 断言结果列 -->
            <el-table-column
              :label="$t('apiTesting.automation.assertions')"
              width="120"
            >
              <template #default="scope">
                <el-popover
                  placement="left"
                  :width="300"
                  trigger="click"
                  v-if="
                    scope.row.assertions_results &&
                    scope.row.assertions_results.length > 0
                  "
                >
                  <template #reference>
                    <el-tag
                      :type="
                        getAssertionsStatusType(scope.row.assertions_results)
                      "
                      size="small"
                      style="cursor: pointer"
                    >
                      {{ getAssertionsSummary(scope.row.assertions_results) }}
                    </el-tag>
                  </template>
                  <div class="assertions-popover">
                    <div
                      v-for="(assertion, idx) in scope.row.assertions_results"
                      :key="idx"
                      class="assertion-popover-item"
                    >
                      <el-tag
                        :type="assertion.passed ? 'success' : 'danger'"
                        size="small"
                        style="margin-right: 8px"
                      >
                        {{ assertion.passed ? "✓" : "✗" }}
                      </el-tag>
                      <span>{{ assertion.message || assertion.type }}</span>
                    </div>
                  </div>
                </el-popover>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <template #footer>
        <el-button @click="showExecutionDialog = false">{{
          $t("apiTesting.common.close")
        }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, nextTick, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  Plus,
  Refresh,
  MoreFilled,
  VideoPlay,
  Edit,
  Folder,
  Document,
  Delete,
  Rank,
} from "@element-plus/icons-vue";
import draggable from "vuedraggable";
import api from "@/utils/api";
import dayjs from "dayjs";

const { t } = useI18n();

// 状态变量
const projects = ref([]);
const selectedProject = ref(null);
const testSuites = ref([]);
const selectedSuite = ref(null);
const executions = ref([]);
const environments = ref([]);
const requestTree = ref([]);
const running = ref(false);
const executionsLoading = ref(false);
const showCreateSuiteDialog = ref(false);
const showAddRequestDialog = ref(false);
const showExecutionDialog = ref(false);
const editingSuite = ref(null);
const submittingSuite = ref(false);
const addingRequests = ref(false);
const currentExecution = ref(null);
const suiteFormRef = ref();
const requestTreeRef = ref();

// 请求排序相关
const sortableRequests = ref([]);
const savingOrder = ref(false);

watch(
  () => selectedSuite.value?.suite_requests,
  (requests) => {
    sortableRequests.value = requests ? [...requests] : [];
  },
  { immediate: true },
);

const onDragEnd = async () => {
  await saveRequestOrder();
};

const saveRequestOrder = async () => {
  if (!selectedSuite.value) return;
  savingOrder.value = true;
  try {
    const orders = sortableRequests.value.map((req, index) => ({
      id: req.id,
      order: index,
    }));
    await api.post(
      `/api-testing/test-suites/${selectedSuite.value.id}/reorder-requests/`,
      { orders },
    );
    // 同步更新 selectedSuite 中的顺序
    selectedSuite.value.suite_requests = [...sortableRequests.value];
    ElMessage.success("排序已保存");
  } catch (error) {
    ElMessage.error("保存排序失败");
  } finally {
    savingOrder.value = false;
  }
};

// 断言编辑相关
const showAssertionDialog = ref(false);
const currentSuiteRequest = ref(null);
const editingAssertions = ref([]);
const submittingAssertions = ref(false);

// 断言类型选项
const assertionTypes = [
  { value: "status_code", label: "状态码" },
  { value: "json_path", label: "JSON路径" },
  { value: "response_time", label: "响应时间" },
  { value: "header", label: "响应头" },
  { value: "body_contains", label: "响应体包含" },
];

const suiteForm = reactive({
  name: "",
  description: "",
  project: null,
  environment: null,
  visibility: "all",
});

const suiteRules = computed(() => ({
  name: [
    {
      required: true,
      message: t("apiTesting.automation.inputSuiteName"),
      trigger: "blur",
    },
  ],
  project: [
    {
      required: true,
      message: t("apiTesting.automation.selectProject"),
      trigger: "change",
    },
  ],
}));

const requestTreeProps = {
  children: "children",
  label: "name",
};

const httpProjects = computed(() => {
  return projects.value.filter(
    (project) => project.project_type !== "WEBSOCKET",
  );
});

// 辅助函数
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
  const typeMap = {
    PENDING: "info",
    RUNNING: "warning",
    COMPLETED: "success",
    FAILED: "danger",
    CANCELLED: "info",
  };
  return typeMap[status] || "info";
};

const getStatusText = (status) => {
  const statusKey = {
    PENDING: "pending",
    RUNNING: "running",
    COMPLETED: "completed",
    FAILED: "failed",
    CANCELLED: "cancelled",
  }[status];
  return statusKey ? t(`apiTesting.automation.status.${statusKey}`) : status;
};

const formatDate = (dateString) => {
  return dayjs(dateString).format("YYYY-MM-DD HH:mm:ss");
};

const getAverageExecutionTime = (execution) => {
  if (
    !execution.results ||
    !Array.isArray(execution.results) ||
    execution.results.length === 0
  ) {
    return "-";
  }

  const totalResponseTime = execution.results.reduce(
    (sum, result) => sum + (result.response_time || 0),
    0,
  );
  const averageTime = totalResponseTime / execution.results.length;

  if (averageTime < 1000) {
    return `${Math.round(averageTime)}ms`;
  } else {
    return `${(averageTime / 1000).toFixed(1)}s`;
  }
};

const getPassRate = (execution) => {
  if (execution.total_requests === 0) return 0;
  return ((execution.passed_requests / execution.total_requests) * 100).toFixed(
    1,
  );
};

const getEnvironmentName = (environmentId) => {
  if (!environmentId) return t("apiTesting.automation.noEnvironment");
  const env = environments.value.find((e) => e.id === environmentId);
  return env ? env.name : t("apiTesting.automation.noEnvironment");
};

// 断言相关辅助函数
const getAssertionsStatusType = (assertions) => {
  if (!assertions || assertions.length === 0) return "info";
  const allPassed = assertions.every((a) => a.passed);
  return allPassed ? "success" : "danger";
};

const getAssertionsSummary = (assertions) => {
  if (!assertions || assertions.length === 0) return "0";
  const passed = assertions.filter((a) => a.passed).length;
  const total = assertions.length;
  return `${passed}/${total}`;
};

// API 调用函数
const loadProjects = async () => {
  try {
    const response = await api.get("/api-testing/projects/");
    projects.value = response.data.results || response.data;

    const httpProjects = projects.value.filter(
      (project) => project.project_type !== "WEBSOCKET",
    );

    if (httpProjects.length > 0 && !selectedProject.value) {
      selectedProject.value = httpProjects[0].id;
      await onProjectChange();
    } else if (httpProjects.length === 0) {
      selectedProject.value = null;
    }
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.loadProjects"));
  }
};

const loadTestSuites = async () => {
  if (!selectedProject.value) return;

  try {
    const response = await api.get("/api-testing/test-suites/", {
      params: { project: selectedProject.value },
    });
    testSuites.value = response.data.results || response.data;
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.loadTestSuites"));
  }
};

const loadEnvironments = async () => {
  try {
    const response = await api.get("/api-testing/environments/");
    const allEnvironments = response.data.results || response.data;

    environments.value = allEnvironments.filter(
      (env) =>
        env.scope === "GLOBAL" ||
        (env.scope === "LOCAL" &&
          (!selectedProject.value || env.project === selectedProject.value)),
    );
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.loadEnvironments"));
  }
};

const loadRequestTree = async () => {
  if (!selectedProject.value) return;

  try {
    const collectionsRes = await api.get("/api-testing/collections/", {
      params: { project: selectedProject.value },
    });
    const collections = collectionsRes.data.results || collectionsRes.data;

    const requestsRes = await api.get("/api-testing/requests/", {
      params: { project: selectedProject.value, page_size: 1000 },
    });
    const requests = requestsRes.data.results || requestsRes.data;

    requestTree.value = buildRequestTree(collections, requests);
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.loadRequestTree"));
  }
};

const buildRequestTree = (collections, requests) => {
  const map = {};
  const roots = [];

  collections.forEach((collection) => {
    map[collection.id] = {
      ...collection,
      type: "collection",
      children: [],
    };
  });

  collections.forEach((collection) => {
    if (collection.parent && map[collection.parent]) {
      map[collection.parent].children.push(map[collection.id]);
    } else {
      roots.push(map[collection.id]);
    }
  });

  requests.forEach((request) => {
    if (map[request.collection]) {
      map[request.collection].children.push({
        ...request,
        type: "request",
        id: `request_${request.id}`,
      });
    }
  });

  return roots;
};

const loadExecutions = async () => {
  if (!selectedSuite.value) return;

  executionsLoading.value = true;
  try {
    const response = await api.get("/api-testing/test-executions/", {
      params: { test_suite: selectedSuite.value.id },
    });
    executions.value = response.data.results || response.data;
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.loadExecutionHistory"));
  } finally {
    executionsLoading.value = false;
  }
};

const onProjectChange = async () => {
  const selectedProjectData = projects.value.find(
    (p) => p.id === selectedProject.value,
  );
  if (selectedProjectData && selectedProjectData.project_type === "WEBSOCKET") {
    ElMessage.warning(t("apiTesting.messages.warning.websocketNotSupported"));
    const httpProjects = projects.value.filter(
      (project) => project.project_type !== "WEBSOCKET",
    );
    if (httpProjects.length > 0) {
      selectedProject.value = httpProjects[0].id;
    } else {
      selectedProject.value = null;
    }
    return;
  }

  selectedSuite.value = null;
  await Promise.all([loadTestSuites(), loadEnvironments(), loadRequestTree()]);
};

const selectSuite = (suite) => {
  selectedSuite.value = suite;
  loadExecutions();
};

const handleSuiteAction = async ({ action, suite }) => {
  switch (action) {
    case "run":
      await runTestSuite(suite);
      break;
    case "edit":
      editSuite(suite);
      break;
    case "duplicate":
      await duplicateSuite(suite);
      break;
    case "delete":
      await deleteSuite(suite);
      break;
  }
};

const runTestSuite = async (suite) => {
  running.value = true;
  try {
    const response = await api.post(
      `/api-testing/test-suites/${suite.id}/execute/`,
    );
    currentExecution.value = response.data;
    showExecutionDialog.value = true;
    await loadExecutions();
    ElMessage.success(t("apiTesting.messages.success.suiteExecuted"));
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.executeSuite"));
  } finally {
    running.value = false;
  }
};

const editSuite = (suite) => {
  editingSuite.value = suite;
  suiteForm.name = suite.name;
  suiteForm.description = suite.description;
  suiteForm.project = suite.project;
  suiteForm.environment = suite.environment || null;
  suiteForm.visibility = suite.visibility || "all";
  showCreateSuiteDialog.value = true;
};

const duplicateSuite = async (suite) => {
  try {
    const newSuite = {
      name: `${suite.name} - ${t("apiTesting.common.copyText")}`,
      description: suite.description,
      project: suite.project,
      environment: suite.environment || null,
    };
    await api.post("/api-testing/test-suites/", newSuite);
    ElMessage.success(t("apiTesting.messages.success.copy"));
    await loadTestSuites();
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.copyFailed"));
  }
};

const deleteSuite = async (suite) => {
  try {
    await ElMessageBox.confirm(
      t("apiTesting.automation.confirmDeleteSuite", { name: suite.name }),
      t("apiTesting.messages.confirm.deleteTitle"),
      {
        confirmButtonText: t("apiTesting.common.confirm"),
        cancelButtonText: t("apiTesting.common.cancel"),
        type: "warning",
      },
    );

    await api.delete(`/api-testing/test-suites/${suite.id}/`);
    ElMessage.success(t("apiTesting.messages.success.delete"));

    if (selectedSuite.value?.id === suite.id) {
      selectedSuite.value = null;
    }
    await loadTestSuites();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(t("apiTesting.messages.error.deleteFailed"));
    }
  }
};

const submitSuiteForm = async () => {
  if (!suiteFormRef.value) return;

  const valid = await suiteFormRef.value.validate().catch(() => false);
  if (!valid) return;

  submittingSuite.value = true;
  try {
    if (editingSuite.value) {
      await api.put(
        `/api-testing/test-suites/${editingSuite.value.id}/`,
        suiteForm,
      );
      ElMessage.success(t("apiTesting.messages.success.suiteUpdated"));
    } else {
      await api.post("/api-testing/test-suites/", suiteForm);
      ElMessage.success(t("apiTesting.messages.success.suiteCreated"));
    }

    showCreateSuiteDialog.value = false;
    await loadTestSuites();
  } catch (error) {
    ElMessage.error(
      editingSuite.value
        ? t("apiTesting.messages.error.updateFailed")
        : t("apiTesting.messages.error.createFailed"),
    );
  } finally {
    submittingSuite.value = false;
  }
};

const resetSuiteForm = () => {
  editingSuite.value = null;
  Object.assign(suiteForm, {
    name: "",
    description: "",
    project: selectedProject.value,
    environment: null,
    visibility: "all",
  });
  suiteFormRef.value?.resetFields();
};

const showAddRequest = async () => {
  await loadRequestTree();
  showAddRequestDialog.value = true;

  nextTick(() => {
    setTimeout(() => {
      if (requestTreeRef.value && selectedSuite.value) {
        const existingRequestIds =
          selectedSuite.value.suite_requests?.map(
            (sr) => `request_${sr.request.id}`,
          ) || [];

        requestTreeRef.value.setCheckedKeys(existingRequestIds, false);
      }
    }, 200);
  });
};

const onRequestCheck = () => {};

const addSelectedRequests = async () => {
  const checkedNodes = requestTreeRef.value.getCheckedNodes();
  const requestIds = checkedNodes
    .filter((node) => node.type === "request")
    .map((node) => node.id.replace("request_", ""));

  if (requestIds.length === 0) {
    ElMessage.warning(t("apiTesting.messages.warning.selectAtLeastOneRequest"));
    return;
  }

  addingRequests.value = true;
  try {
    await api.post(
      `/api-testing/test-suites/${selectedSuite.value.id}/add-requests/`,
      {
        request_ids: requestIds,
      },
    );

    ElMessage.success(t("apiTesting.messages.success.addSuccess"));
    showAddRequestDialog.value = false;
    await reloadCurrentSuite();
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.addFailed"));
  } finally {
    addingRequests.value = false;
  }
};

const updateRequestEnabled = async (suiteRequest) => {
  try {
    await api.put(`/api-testing/test-suite-requests/${suiteRequest.id}/`, {
      enabled: suiteRequest.enabled,
    });
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.updateFailed"));
    suiteRequest.enabled = !suiteRequest.enabled;
  }
};

// 断言编辑功能
const editAssertions = (suiteRequest) => {
  currentSuiteRequest.value = suiteRequest;
  // 深拷贝断言数组，避免直接修改原数据
  editingAssertions.value = suiteRequest.assertions
    ? JSON.parse(JSON.stringify(suiteRequest.assertions))
    : [];
  showAssertionDialog.value = true;
};

const onAssertionTypeChange = (assertion) => {
  // 根据断言类型重置字段
  switch (assertion.type) {
    case "status_code":
      assertion.operator = assertion.operator || "eq";
      assertion.expected = assertion.expected || 200;
      break;
    case "json_path":
      assertion.operator = assertion.operator || "eq";
      assertion.path = assertion.path || "";
      assertion.expected = assertion.expected || "";
      break;
    case "response_time":
      assertion.operator = assertion.operator || "lt";
      assertion.value = assertion.value || 1000;
      break;
    case "header":
      assertion.operator = assertion.operator || "exists";
      assertion.key = assertion.key || "";
      assertion.value = assertion.value || "";
      break;
    case "body_contains":
      assertion.value = assertion.value || "";
      break;
  }
};

const addAssertion = () => {
  editingAssertions.value.push({
    type: "status_code",
    operator: "eq",
    expected: 200,
    enabled: true,
  });
};

const removeAssertion = (index) => {
  editingAssertions.value.splice(index, 1);
};

const saveAssertions = async () => {
  if (!currentSuiteRequest.value) return;

  submittingAssertions.value = true;
  try {
    await api.put(
      `/api-testing/test-suite-requests/${currentSuiteRequest.value.id}/`,
      {
        assertions: editingAssertions.value,
      },
    );

    // 更新本地数据
    currentSuiteRequest.value.assertions = editingAssertions.value;

    ElMessage.success(t("apiTesting.messages.success.assertionsUpdated"));
    showAssertionDialog.value = false;
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.updateFailed"));
  } finally {
    submittingAssertions.value = false;
  }
};

const removeRequest = async (suiteRequest) => {
  try {
    await ElMessageBox.confirm(
      t("apiTesting.automation.confirmRemoveRequest"),
      t("apiTesting.automation.confirmRemove"),
      {
        confirmButtonText: t("apiTesting.common.confirm"),
        cancelButtonText: t("apiTesting.common.cancel"),
        type: "warning",
      },
    );

    await api.delete(`/api-testing/test-suite-requests/${suiteRequest.id}/`);
    ElMessage.success(t("apiTesting.messages.success.removeSuccess"));
    await reloadCurrentSuite();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(t("apiTesting.messages.error.removeFailed"));
    }
  }
};

const reloadCurrentSuite = async () => {
  if (!selectedSuite.value) return;

  try {
    const response = await api.get(
      `/api-testing/test-suites/${selectedSuite.value.id}/`,
    );
    const updatedSuite = response.data;

    selectedSuite.value = { ...updatedSuite };
    sortableRequests.value = [...(updatedSuite.suite_requests || [])];

    const index = testSuites.value.findIndex(
      (suite) => suite.id === updatedSuite.id,
    );
    if (index !== -1) {
      testSuites.value[index] = { ...updatedSuite };
    }
  } catch (error) {
    ElMessage.error(t("apiTesting.messages.error.refreshSuiteFailed"));
  }
};

const viewExecutionDetail = (execution) => {
  currentExecution.value = execution;
  showExecutionDialog.value = true;
};

const formatExecutionResults = (results) => {
  if (!results || !Array.isArray(results)) return [];
  return results;
};

onMounted(() => {
  loadProjects();
});
</script>

<style scoped>
.automation-testing {
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

.content-layout {
  display: flex;
  flex: 1;
  gap: 20px;
  overflow: hidden;
}

.sidebar {
  width: 300px;
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.project-selector {
  background: white;
  padding: 15px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.suite-list {
  background: white;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 15px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
  font-weight: 500;
}

.suite-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px;
  border-bottom: 1px solid #f5f7fa;
  cursor: pointer;
  transition: background-color 0.3s;
}

.suite-item:hover {
  background: #f5f7fa;
}

.suite-item.active {
  background: #e1f3d8;
  border-color: #67c23a;
}

.suite-info {
  flex: 1;
}

.suite-name {
  font-weight: 500;
  margin-bottom: 4px;
}

.suite-meta {
  font-size: 12px;
  color: #909399;
}

.main-content {
  flex: 1;
  background: white;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.suite-detail {
  flex: 1;
  padding: 20px;
  overflow: auto;
}

.suite-header {
  margin-bottom: 30px;
}

.suite-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.suite-title h4 {
  margin: 0;
  color: #303133;
}

.suite-actions {
  display: flex;
  gap: 10px;
}

.suite-description {
  color: #606266;
  margin-bottom: 10px;
}

.suite-meta {
  display: flex;
  gap: 15px;
  align-items: center;
}

.meta-text {
  font-size: 12px;
  color: #909399;
}

.requests-section,
.executions-section {
  margin-bottom: 30px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.section-header h5 {
  margin: 0;
  color: #303133;
  font-size: 16px;
}

.add-request-content {
  max-height: 400px;
  overflow-y: auto;
}

.request-tree-node {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 1;
}

.method-tag {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 2px;
  color: white;
  font-weight: bold;
  margin-left: auto;
}

.method-tag.get {
  background: #67c23a;
}
.method-tag.post {
  background: #409eff;
}
.method-tag.put {
  background: #e6a23c;
}
.method-tag.delete {
  background: #f56c6c;
}
.method-tag.patch {
  background: #909399;
}

.execution-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.execution-summary {
  margin-bottom: 30px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 6px;
}

.execution-results h4 {
  margin: 0 0 15px 0;
  color: #303133;
}

/* 断言编辑器样式 */
.assertions-editor {
  max-height: 500px;
  overflow-y: auto;
}

.assertions-header {
  margin-bottom: 16px;
  display: flex;
  justify-content: flex-end;
}

.empty-assertions {
  padding: 40px 0;
}

.assertions-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.assertion-item {
  background: #f8f9fa;
  border-radius: 6px;
  padding: 12px;
  border: 1px solid #e4e7ed;
}

.assertion-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.assertion-message {
  margin-top: 8px;
  padding-left: 128px;
}

/* 断言弹窗样式 */
.assertions-popover {
  max-height: 300px;
  overflow-y: auto;
  padding: 8px 0;
}

.assertion-popover-item {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-bottom: 1px solid #f0f0f0;
}

.assertion-popover-item:last-child {
  border-bottom: none;
}

/* 可拖拽请求列表表格 */
.drag-table {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}

.drag-table-header,
.drag-table-row {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #ebeef5;
}

.drag-table-header {
  background: #f5f7fa;
  font-size: 12px;
  color: #909399;
  font-weight: 500;
  padding: 10px 0;
}

.drag-table-row {
  background: #fff;
  padding: 10px 0;
  transition: background-color 0.2s;
}

.drag-table-row:last-child {
  border-bottom: none;
}

.drag-table-row:hover {
  background: #f5f7fa;
}

.drag-table-row.disabled {
  opacity: 0.5;
}

.drag-col {
  padding: 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.drag-col-handle {
  width: 40px;
  flex-shrink: 0;
  text-align: center;
}

.drag-col-index {
  width: 40px;
  flex-shrink: 0;
  text-align: center;
  color: #909399;
}

.drag-col-name {
  flex: 2;
  min-width: 0;
}

.drag-col-method {
  width: 80px;
  flex-shrink: 0;
}

.drag-col-url {
  flex: 3;
  min-width: 0;
  color: #606266;
}

.drag-col-enabled {
  width: 80px;
  flex-shrink: 0;
}

.drag-col-assertions {
  width: 80px;
  flex-shrink: 0;
  text-align: center;
}

.drag-col-actions {
  width: 160px;
  flex-shrink: 0;
}

.drag-handle {
  cursor: grab;
  color: #c0c4cc;
  font-size: 16px;
  transition: color 0.2s;
}

.drag-handle:hover {
  color: #409eff;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-table-empty {
  padding: 20px 0;
  text-align: center;
}
</style>
