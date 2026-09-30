import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import { fileURLToPath, URL } from "node:url";

// Element Plus 按需引入：
// - 组件/指令（el-xxx、v-loading）由 unplugin-vue-components 在编译期自动 import
// - ElMessage / ElMessageBox 等 API 可由 unplugin-auto-import 自动 import
// - 样式仍在 main.js 全量引入 element-plus/dist/index.css（importStyle: false），
//   避免显式 import 的组件和命令式 API（MessageBox/Loading 等）丢失样式
const elementPlusResolver = ElementPlusResolver({ importStyle: false });

// 大体积第三方依赖拆分为独立 chunk，便于浏览器长期缓存
const vendorChunks = [
  ["echarts", /[\\/]node_modules[\\/](echarts|zrender)[\\/]/],
  ["xlsx", /[\\/]node_modules[\\/]xlsx[\\/]/],
  ["curlconverter", /[\\/]node_modules[\\/](curlconverter|web-tree-sitter)[\\/]/],
  // Vue 生态、Element Plus 及其图标/依赖放在同一个 chunk：它们首屏都会加载（图标全局注册），
  // 分开会互相引用形成循环 chunk（element-plus / icons <-> vue-vendor），有模块初始化顺序风险
  [
    "vue-vendor",
    /[\\/]node_modules[\\/](vue|@vue|vue-router|pinia|vue-i18n|@intlify|element-plus|@element-plus|@vueuse|@floating-ui|@popperjs|@ctrl|async-validator|dayjs|lodash-es|lodash-unified|memoize-one|normalize-wheel-es)[\\/]/,
  ],
];

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      resolvers: [elementPlusResolver],
      dts: false,
    }),
    Components({
      resolvers: [elementPlusResolver],
      // 只解析第三方组件，不自动注册 src/components 下的本地组件
      dirs: [],
      dts: false,
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  optimizeDeps: {
    esbuildOptions: {
      // curlconverter 的浏览器解析器（web-tree-sitter）使用了 top-level await
      target: "es2022",
    },
    // tree-sitter 是 curlconverter 的 Node 原生依赖，浏览器端走 web-tree-sitter，不参与预构建
    exclude: ["tree-sitter"],
  },
  build: {
    target: "es2022",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          for (const [name, pattern] of vendorChunks) {
            if (pattern.test(id)) return name;
          }
          return undefined;
        },
      },
    },
  },
  server: {
    port: 3000,
    host: "0.0.0.0",
    headers: {
      "Cache-Control": "no-cache, no-store, must-revalidate",
      Pragma: "no-cache",
      Expires: "0",
    },
    proxy: {
      "^/api/": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        secure: false,
      },
      "^/media/": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        secure: false,
      },
      "^/ws/": {
        target: "ws://127.0.0.1:8001",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        api: "modern-compiler",
      },
    },
  },
});
