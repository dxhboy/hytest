<template>
  <div class="notification-content">
    <div v-if="parsedContent" class="notification-content-parsed">
      <div
        class="content-item"
        v-for="(item, index) in parsedContent"
        :key="index"
      >
        <span class="content-label">{{ item.label }}:</span>
        <span class="content-value">{{ item.value }}</span>
      </div>
    </div>
    <div v-else class="notification-content-raw">
      <pre>{{ content || "-" }}</pre>
    </div>
  </div>
</template>

<script setup>
// 通知日志详情中的"通知内容"展示：
// 尝试把 Webhook(JSON: 企业微信/钉钉 markdown、飞书 interactive 卡片) 或
// 邮件纯文本内容解析为「标签: 值」列表，解析失败时原样显示
import { computed } from "vue";

const props = defineProps({
  content: {
    type: String,
    default: "",
  },
});

// 把 "标签: 值" 形式的多行文本解析为列表，解析不到任何条目时返回 null
const parseLines = (text, { skipLine, skipValue } = {}) => {
  const result = [];
  text
    .split("\n")
    .filter((line) => line.trim())
    .forEach((line) => {
      if (skipLine && skipLine(line)) return;
      const colonIndex = line.indexOf(":");
      if (colonIndex <= 0) return;
      const label = line.substring(0, colonIndex).trim();
      const value = line.substring(colonIndex + 1).trim();
      if (label && value && !(skipValue && skipValue(value))) {
        result.push({ label, value });
      }
    });
  return result.length > 0 ? result : null;
};

const parsedContent = computed(() => {
  const content = props.content;
  if (!content) return null;

  // 尝试解析 JSON 格式的通知内容(Webhook)
  try {
    const jsonContent = JSON.parse(content);
    let contentText = "";

    if (jsonContent.msgtype === "markdown" && jsonContent.markdown) {
      // 钉钉(text) / 企业微信(content) 格式
      contentText = jsonContent.markdown.text || jsonContent.markdown.content;
    } else if (jsonContent.msg_type === "interactive" && jsonContent.card) {
      // 飞书卡片格式
      contentText = jsonContent.card.elements?.[0]?.text?.content;
    }

    if (contentText) {
      // 跳过标题行(包含**的行)
      return parseLines(contentText, {
        skipLine: (line) => line.includes("**"),
      });
    }
  } catch (e) {
    // JSON 解析失败，按纯文本(邮件通知)解析
  }

  // 纯文本格式：过滤掉包含详细测试结果的超长值
  return parseLines(content, {
    skipValue: (value) =>
      value.includes("'results':") || value.includes('"results":'),
  });
});
</script>

<style scoped>
.notification-content {
  width: 100%;
}

.notification-content-parsed {
  background: #ffffff;
  border-radius: 8px;
  padding: 20px;
  border: 1px solid #e4e7ed;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.content-item {
  display: flex;
  align-items: flex-start;
  padding: 12px 0;
  border-bottom: 1px solid #f0f2f5;
}

.content-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.content-item:first-child {
  padding-top: 0;
}

.content-label {
  font-weight: 600;
  color: #606266;
  min-width: 100px;
  flex-shrink: 0;
  margin-right: 16px;
  font-size: 14px;
  line-height: 1.8;
}

.content-value {
  color: #303133;
  flex: 1;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.8;
}

.notification-content-raw pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
  max-height: 400px;
  overflow-y: auto;
}

.notification-content-raw pre::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.notification-content-raw pre::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}

.notification-content-raw pre::-webkit-scrollbar-thumb:hover {
  background: #a8abb2;
}
</style>
