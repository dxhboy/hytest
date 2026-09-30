import { createApp } from "vue";
import { createPinia } from "pinia";
// Element Plus 组件由 unplugin-vue-components 按需引入（见 vite.config.js），
// 样式保持全量引入，保证 ElMessageBox / ElLoading 等命令式 API 样式完整
import "element-plus/dist/index.css";
import * as ElementPlusIconsVue from "@element-plus/icons-vue";
import { useUserStore } from "@/stores/user";
import i18n from "./locales";

import App from "./App.vue";
import router from "./router";
import "./assets/css/global.scss";

const app = createApp(App);

const pinia = createPinia();
app.use(pinia);

async function init() {
  try {
    const userStore = useUserStore();
    await userStore.initAuth();
  } catch (error) {
    // 获取用户信息失败，说明未登录，无需处理
  }

  // 注册所有图标（模板中大量以全局组件名及 <component :is="'Xxx'"> 字符串形式使用）
  for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
    app.component(key, component);
  }

  app.use(router);
  app.use(i18n);

  // Element Plus 语言由 App.vue 的 el-config-provider 动态配置
  app.mount("#app");
}

init();
