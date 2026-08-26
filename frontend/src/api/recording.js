import request from "@/utils/api";

// 创建录制会话
export function startRecording(data) {
  return request({
    url: "/ui-automation/recording/start/",
    method: "post",
    data,
  });
}

// 停止录制并触发元素匹配
export function stopRecording(sessionId) {
  return request({
    url: `/ui-automation/recording/${sessionId}/stop/`,
    method: "post",
  });
}

// 获取元素匹配结果
export function getMatchResults(sessionId) {
  return request({
    url: `/ui-automation/recording/${sessionId}/match-results/`,
    method: "get",
  });
}

// 确认录制结果并保存
export function confirmRecording(sessionId, data) {
  return request({
    url: `/ui-automation/recording/${sessionId}/confirm/`,
    method: "post",
    data,
  });
}

// 取消录制会话
export function cancelRecording(sessionId) {
  return request({
    url: `/ui-automation/recording/${sessionId}/cancel/`,
    method: "post",
  });
}
