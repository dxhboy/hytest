import { createRouter, createWebHistory } from "vue-router";
import { useUserStore } from "@/stores/user";

// 登录页和布局组件静态导入（首屏必需），其余页面全部按路由懒加载
import Login from "@/views/auth/Login.vue";
import Layout from "@/layout/index.vue";

const routes = [
  {
    path: "/",
    redirect: "/home",
  },
  {
    path: "/home",
    name: "Home",
    component: () => import("@/views/Home.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/login",
    name: "Login",
    component: Login,
    meta: { requiresGuest: true },
  },
  {
    path: "/register",
    name: "Register",
    component: () => import("@/views/auth/Register.vue"),
    meta: { requiresGuest: true },
  },
  {
    path: "/ai-generation/assistant",
    name: "Assistant",
    component: () => import("@/views/assistant/AssistantView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/ai-generation",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "requirement-analysis",
      },
      {
        path: "requirement-analysis",
        name: "RequirementAnalysis",
        component: () =>
          import("@/views/requirement-analysis/RequirementAnalysisView.vue"),
      },
      {
        path: "projects",
        name: "Projects",
        component: () => import("@/views/projects/ProjectList.vue"),
      },
      {
        path: "projects/:id",
        name: "ProjectDetail",
        component: () => import("@/views/projects/ProjectDetail.vue"),
      },
      {
        path: "testcases",
        name: "TestCases",
        component: () => import("@/views/testcases/TestCaseList.vue"),
      },
      {
        path: "testcases/create",
        name: "CreateTestCase",
        component: () => import("@/views/testcases/TestCaseForm.vue"),
      },
      {
        path: "testcases/:id",
        name: "TestCaseDetail",
        component: () => import("@/views/testcases/TestCaseDetail.vue"),
      },
      {
        path: "testcases/:id/edit",
        name: "EditTestCase",
        component: () => import("@/views/testcases/TestCaseEdit.vue"),
      },
      {
        path: "versions",
        name: "Versions",
        component: () => import("@/views/versions/VersionList.vue"),
      },
      {
        path: "reviews",
        name: "Reviews",
        component: () => import("@/views/reviews/ReviewList.vue"),
      },
      {
        path: "reviews/create",
        name: "CreateReview",
        component: () => import("@/views/reviews/ReviewForm.vue"),
      },
      {
        path: "reviews/:id",
        name: "ReviewDetail",
        component: () => import("@/views/reviews/ReviewDetail.vue"),
      },
      {
        path: "reviews/:id/edit",
        name: "EditReview",
        component: () => import("@/views/reviews/ReviewForm.vue"),
      },
      {
        path: "review-templates",
        name: "ReviewTemplates",
        component: () => import("@/views/reviews/ReviewTemplateList.vue"),
      },
      {
        path: "testsuites",
        name: "TestSuites",
        component: () => import("@/views/testsuites/TestSuiteList.vue"),
      },
      {
        path: "executions",
        name: "Executions",
        component: () => import("@/views/executions/ExecutionListView.vue"),
      },
      {
        path: "executions/:id",
        name: "ExecutionDetail",
        component: () => import("@/views/executions/ExecutionDetailView.vue"),
      },
      {
        path: "reports",
        name: "AiTestReport",
        component: () => import("@/views/reports/AiTestReport.vue"),
      },
      {
        path: "generated-testcases",
        name: "GeneratedTestCases",
        component: () =>
          import("@/views/requirement-analysis/GeneratedTestCaseList.vue"),
      },
      {
        path: "task-detail/:taskId",
        name: "TaskDetail",
        component: () => import("@/views/requirement-analysis/TaskDetail.vue"),
      },
      {
        path: 'scheduled-generation',
        name: 'ScheduledGenerationTasks',
        component: () =>
          import('@/views/requirement-analysis/ScheduledGenerationTasks.vue'),
      },
      {
        path: 'jira-import',
        name: 'JiraImport',
        component: () => import('@/views/requirement-analysis/JiraImport.vue'),
      },
      {
        path: "profile",
        name: "Profile",
        component: () => import("@/views/profile/UserProfile.vue"),
      },
    ],
  },
  {
    path: "/api-testing",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "dashboard",
      },
      {
        path: "dashboard",
        name: "ApiDashboard",
        component: () => import("@/views/api-testing/Dashboard.vue"),
        meta: { module: 'api-testing', page: 'dashboard' },
      },
      {
        path: "projects",
        name: "ApiProjects",
        component: () => import("@/views/api-testing/ProjectManagement.vue"),
        meta: { module: 'api-testing', page: 'projects' },
      },
      {
        path: "interfaces",
        name: "ApiInterfaces",
        component: () => import("@/views/api-testing/InterfaceManagement.vue"),
        meta: { module: 'api-testing', page: 'interface-management' },
      },
      {
        path: "automation",
        name: "ApiAutomation",
        component: () => import("@/views/api-testing/AutomationTesting.vue"),
        meta: { module: 'api-testing', page: 'automation-testing' },
      },
      {
        path: "history",
        name: "ApiHistory",
        component: () => import("@/views/api-testing/RequestHistory.vue"),
        meta: { module: 'api-testing', page: 'history' },
      },
      {
        path: "environments",
        name: "ApiEnvironments",
        component: () => import("@/views/api-testing/EnvironmentManagement.vue"),
        meta: { module: 'api-testing', page: 'environments' },
      },
      {
        path: "reports",
        name: "ApiReports",
        component: () => import("@/views/api-testing/ReportView.vue"),
        meta: { module: 'api-testing', page: 'reports' },
      },
      {
        path: "scheduled-tasks",
        name: "ApiScheduledTasks",
        component: () => import("@/views/api-testing/ScheduledTasks.vue"),
        meta: { module: 'api-testing', page: 'scheduled-tasks' },
      },
      {
        path: "ai-service-config",
        name: "ApiAIServiceConfig",
        component: () => import("@/views/api-testing/AIServiceConfig.vue"),
      },
      {
        path: "notification-logs",
        name: "ApiNotificationLogs",
        component: () => import("@/views/notification/NotificationLogs.vue"),
      },
    ],
  },
  {
    path: "/ui-automation",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "dashboard",
      },
      {
        path: "dashboard",
        name: "UiDashboard",
        component: () => import("@/views/ui-automation/dashboard/Dashboard.vue"),
        meta: { module: 'ui-automation', page: 'dashboard' },
      },
      {
        path: "projects",
        name: "UiProjects",
        component: () => import("@/views/ui-automation/projects/ProjectList.vue"),
        meta: { module: 'ui-automation', page: 'projects' },
      },
      {
        path: "elements-enhanced",
        name: "UiElementsEnhanced",
        component: () => import("@/views/ui-automation/elements/ElementManagerEnhanced.vue"),
        meta: { module: 'ui-automation', page: 'elements' },
      },
      {
        path: "test-cases",
        name: "UiTestCases",
        component: () => import("@/views/ui-automation/test-cases/TestCaseManager.vue"),
        meta: { module: 'ui-automation', page: 'test-cases' },
      },
      {
        path: "scripts-enhanced",
        name: "UiScriptsEnhanced",
        component: () => import("@/views/ui-automation/scripts/ScriptEditorEnhanced.vue"),
        meta: { module: 'ui-automation', page: 'scripts' },
      },
      {
        path: "scripts/editor",
        name: "UiScriptEditor",
        component: () => import("@/views/ui-automation/scripts/ScriptEditorEnhanced.vue"),
      },
      {
        path: "scripts",
        name: "UiScripts",
        component: () => import("@/views/ui-automation/scripts/ScriptList.vue"),
      },
      {
        path: "suites",
        name: "UiSuites",
        component: () => import("@/views/ui-automation/suites/SuiteList.vue"),
        meta: { module: 'ui-automation', page: 'suites' },
      },
      {
        path: "executions",
        name: "UiExecutions",
        component: () => import("@/views/ui-automation/executions/ExecutionList.vue"),
        meta: { module: 'ui-automation', page: 'executions' },
      },
      {
        path: "reports",
        name: "UiReports",
        component: () => import("@/views/ui-automation/reports/ReportList.vue"),
        meta: { module: 'ui-automation', page: 'reports' },
      },
      {
        path: "scheduled-tasks",
        name: "UiScheduledTasks",
        component: () => import("@/views/ui-automation/scheduled-tasks/ScheduledTasks.vue"),
        meta: { module: 'ui-automation', page: 'scheduled-tasks' },
      },
      {
        path: "notification-logs",
        name: "UiNotificationLogs",
        component: () => import("@/views/ui-automation/notification/NotificationLogs.vue"),
      },
      {
        path: "parameters",
        name: "UiProjectParameters",
        component: () =>
          import("@/views/configuration/ProjectParameters.vue"),
        meta: { module: 'ui-automation', page: 'parameters' },
      },
      {
        path: "recorder",
        name: "UiRecorder",
        component: () => import("@/views/ui-automation/recorder/RecorderView.vue"),
        meta: { module: 'ui-automation', page: 'recorder' },
      },
    ],
  },
  {
    path: "/ai-intelligent-mode",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        redirect: "testing",
      },
      {
        path: "testing",
        name: "AITesting",
        component: () => import("@/views/ui-automation/ai/AITesting.vue"),
      },
      {
        path: "cases",
        name: "AICaseList",
        component: () => import("@/views/ui-automation/ai/AICaseList.vue"),
      },
      {
        path: "execution-records",
        name: "AIExecutionRecords",
        component: () => import("@/views/ui-automation/ai/AIExecutionRecords.vue"),
      },
    ],
  },
  {
    path: "/data-factory",
    name: "DataFactory",
    component: () => import("@/views/data-factory/DataFactory.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/configuration",
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: "",
        component: () =>
          import("@/views/configuration/ConfigurationCenter.vue"),
        children: [
          {
            path: "",
            redirect: "ai-model",
          },
          {
            path: "ai-model",
            name: "ConfigAIModel",
            component: () =>
              import("@/views/requirement-analysis/AIModelConfig.vue"),
          },
          {
            path: "prompt-config",
            name: "ConfigPromptConfig",
            component: () =>
              import("@/views/requirement-analysis/PromptConfig.vue"),
          },
          {
            path: "generation-config",
            name: "ConfigGenerationConfig",
            component: () =>
              import("@/views/requirement-analysis/GenerationConfigView.vue"),
          },
          {
            path: "ui-env",
            name: "ConfigUIEnv",
            component: () =>
              import("@/views/configuration/UIEnvironmentConfig.vue"),
          },
          {
            path: "ai-mode",
            name: "ConfigAIMode",
            component: () =>
              import("@/views/configuration/AIIntelligentModeConfig.vue"),
          },
          {
            path: "notification",
            name: "ConfigNotification",
            component: () =>
              import("@/views/configuration/NotificationConfig.vue"),
          },
          {
            path: "remote-browser",
            name: "ConfigRemoteBrowser",
            component: () =>
              import("@/views/configuration/RemoteBrowserConfig.vue"),
          },
          {
            path: "dify",
            name: "DifyConfig",
            component: () => import("@/views/configuration/DifyConfig.vue"),
          },
          {
            path: "projects",
            name: "ConfigProjectCenter",
            component: () => import("@/views/configuration/ProjectCenter.vue"),
          },
          {
            path: "knowledge-base",
            name: "ConfigKnowledgeBase",
            component: () =>
              import("@/views/configuration/KnowledgeBase.vue"),
          },
        ],
      },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    name: "NotFound",
    component: () => import("@/views/NotFound.vue"),
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  // 认证状态已在 main.js 挂载路由前通过 userStore.initAuth() 初始化
  const userStore = useUserStore();

  if (to.meta.requiresAuth && !userStore.isAuthenticated) {
    return "/login";
  }
  if (to.meta.requiresGuest && userStore.isAuthenticated) {
    return "/home";
  }
  return true;
});

export default router;
