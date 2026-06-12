<template>
  <div class="message-bubble" :class="[`bubble--${msg.role}`]">
    <div class="bubble-avatar">
      <el-icon v-if="msg.role === 'user'"><UserFilled /></el-icon>
      <el-icon v-else><Cpu /></el-icon>
    </div>
    <div class="bubble-content">
      <div class="bubble-text" v-html="renderedContent" />
      <div v-if="msg.tool_name" class="bubble-tools">
        <el-tag size="small" type="info" v-for="t in toolNames" :key="t">{{ t }}</el-tag>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { UserFilled, Cpu } from '@element-plus/icons-vue'

const props = defineProps({
  msg: { type: Object, required: true },
})

const toolNames = computed(() =>
  props.msg.tool_name ? props.msg.tool_name.split(',').filter(Boolean) : []
)

const renderedContent = computed(() => {
  let text = props.msg.content || ''
  const codeBlocks = []
  // 先提取代码块，用占位符替换，避免对其内容做额外处理
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length
    codeBlocks.push(`<pre class="code-block"><code>${escapeHtml(code.trim())}</code></pre>`)
    return `\x00CODEBLOCK${idx}\x00`
  })
  // 对剩余文本全量转义（防止普通文本中的 HTML 注入）
  text = escapeHtml(text)
  // 提取行内代码（此时文本已转义，需要还原 ` ` 周围的内容）
  text = text.replace(/`([^`]+)`/g, (_, code) => `<code class="inline-code">${code}</code>`)
  // 换行转 <br>
  text = text.replace(/\n/g, '<br />')
  // 还原代码块占位符
  text = text.replace(/\x00CODEBLOCK(\d+)\x00/g, (_, i) => codeBlocks[Number(i)])
  return text
})

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
</script>

<style scoped>
.message-bubble {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.bubble--user {
  flex-direction: row-reverse;
}
.bubble-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.bubble--user .bubble-avatar {
  background: #409eff22;
  color: #409eff;
}
.bubble-content {
  max-width: 80%;
}
.bubble-text {
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
  background: #f5f5f5;
  color: #303030;
}
.bubble--user .bubble-text {
  background: #409eff;
  color: #fff;
}
.bubble-tools {
  margin-top: 4px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.code-block {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  margin: 4px 0;
}
.inline-code {
  background: #f0f0f0;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
  color: #c0392b;
}
</style>
