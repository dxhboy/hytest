import axios from "axios";
import { ElMessage } from "element-plus";
import { useUserStore } from "@/stores/user";
import i18n from "@/locales";

const t = (key) => i18n.global.t(key);

const api = axios.create({
  baseURL: "/api",
  timeout: 30000,
  // 回退到 Session 认证时，Django 要求携带 CSRF token
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
  headers: {
    "Content-Type": "application/json",
  },
});

// 正在刷新的标志
let isRefreshing = false;
// 等待刷新的请求队列
let failedQueue = [];

// 处理队列中的请求
const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });

  failedQueue = [];
};

// 请求拦截器
api.interceptors.request.use(
  async (config) => {
    const userStore = useUserStore();

    // 检查是否是刷新token的请求
    if (config.url === "/auth/token/refresh/") {
      return config;
    }

    // 如果有access token
    if (userStore.accessToken) {
      // 检查token是否即将过期（5分钟内）
      if (userStore.isTokenExpiringSoon && !userStore.isTokenExpired) {
        // 如果没有正在刷新，开始刷新
        if (!isRefreshing) {
          isRefreshing = true;

          try {
            const newToken = await userStore.refreshAccessToken();
            processQueue(null, newToken);

            // 更新当前请求的token
            config.headers.Authorization = `Bearer ${newToken}`;
          } catch (error) {
            console.error("Token刷新失败:", error);
            processQueue(error, null);
            // 刷新失败会在user store中自动logout
            return Promise.reject(error);
          } finally {
            isRefreshing = false;
          }
        } else {
          // 如果正在刷新，将请求加入队列
          return new Promise((resolve, reject) => {
            failedQueue.push({ resolve, reject });
          })
            .then((token) => {
              config.headers.Authorization = `Bearer ${token}`;
              return config;
            })
            .catch((err) => {
              return Promise.reject(err);
            });
        }
      }

      // 使用Bearer token格式
      config.headers.Authorization = `Bearer ${userStore.accessToken}`;
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const userStore = useUserStore();
    const originalRequest = error.config;

    // 如果是401错误且不是刷新token的请求
    if (error.response?.status === 401 && !originalRequest._retry) {
      // 如果是logout请求失败，直接清除本地状态不再重试logout，防止死循环
      if (originalRequest.url === "/auth/logout/") {
        userStore.clearAuth();
        window.location.href = "/login";
        return Promise.reject(error);
      }

      // 如果是刷新token的请求失败
      if (originalRequest.url === "/auth/token/refresh/") {
        await userStore.logout();
        return Promise.reject(error);
      }

      // 如果有refresh token，尝试刷新
      if (userStore.refreshToken && !isRefreshing) {
        originalRequest._retry = true;
        isRefreshing = true;

        try {
          const newToken = await userStore.refreshAccessToken();
          processQueue(null, newToken);

          // 更新当前请求的token
          originalRequest.headers.Authorization = `Bearer ${newToken}`;

          // 重试原请求
          return api(originalRequest);
        } catch (refreshError) {
          console.error("Token刷新失败:", refreshError);
          processQueue(refreshError, null);
          await userStore.logout();
          return Promise.reject(refreshError);
        } finally {
          isRefreshing = false;
        }
      } else {
        // 没有refresh token，直接退出
        await userStore.logout();
      }

      return Promise.reject(error);
    }

    // 其他错误处理
    if (error.response?.status === 401) {
      ElMessage.error(t("common.request.sessionExpired"));
    } else if (error.response?.status >= 500) {
      ElMessage.error(t("common.request.serverError"));
    } else if (error.response?.data?.error) {
      ElMessage.error(error.response.data.error);
    } else if (error.response?.data?.detail) {
      ElMessage.error(error.response.data.detail);
    }

    return Promise.reject(error);
  },
);

export default api;
