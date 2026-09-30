<template>
  <div class="home-container">
    <!-- Animated background particles -->
    <div class="bg-particles">
      <div v-for="n in 6" :key="n" class="particle" :class="'p' + n"></div>
    </div>

    <div class="content-wrapper">
      <!-- Top bar -->
      <header class="top-bar">
        <div class="logo-area">
          <div class="logo-icon">
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="32" height="32" rx="8" fill="url(#logo-grad)" />
              <path d="M8 12h16M8 16h10M8 20h13" stroke="#fff" stroke-width="2" stroke-linecap="round" />
              <circle cx="24" cy="20" r="4" fill="#fff" fill-opacity="0.3" />
              <path d="M23 20l1 1 2-2.5" stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              <defs>
                <linearGradient id="logo-grad" x1="0" y1="0" x2="32" y2="32">
                  <stop stop-color="#6366f1" />
                  <stop offset="1" stop-color="#8b5cf6" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <span class="logo-text">HyTest</span>
        </div>

        <div class="header-actions">
          <el-dropdown @command="handleLanguageChange" class="lang-switch">
            <span class="action-btn">
              <span class="lang-flag">{{ currentLanguage === 'zh-cn' ? 'CN' : 'EN' }}</span>
              <span class="lang-label">{{ $t('home.language.current') }}</span>
              <el-icon class="el-icon--right"><arrow-down /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="zh-cn" :disabled="currentLanguage === 'zh-cn'">
                  {{ $t('home.language.zhCN') }}
                </el-dropdown-item>
                <el-dropdown-item command="en" :disabled="currentLanguage === 'en'">
                  {{ $t('home.language.en') }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-dropdown @command="handleCommand">
            <span class="action-btn user-btn">
              <el-avatar :size="30" :icon="UserFilled" class="user-avatar" />
              <span class="username">{{ userStore.user?.username || $t('home.user') }}</span>
              <el-icon class="el-icon--right"><arrow-down /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">{{ $t('home.logout') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- Hero section -->
      <section class="hero">
        <h1 class="hero-title">
          <span class="title-line">{{ $t('home.title') }}</span>
        </h1>
      </section>

      <!-- Feature cards -->
      <section class="cards-grid">
        <div
          v-for="(card, index) in cards"
          :key="card.type"
          class="feature-card"
          :class="'card-' + card.type"
          :style="{ '--delay': index * 0.08 + 's' }"
          @click="handleNavigate(card.type)"
          role="button"
          tabindex="0"
        >
          <div class="card-glow"></div>
          <div class="card-body">
            <div class="icon-wrapper" :class="'icon-' + card.type">
              <el-icon><component :is="card.icon" /></el-icon>
            </div>
            <div class="card-text">
              <h3>{{ $t(card.titleKey) }}</h3>
              <p>{{ $t(card.descKey) }}</p>
            </div>
            <div class="card-arrow">
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  MagicStick,
  Link,
  Monitor,
  DataLine,
  Cpu,
  Setting,
  ChatDotRound,
  UserFilled,
  ArrowDown,
  ArrowRight,
} from '@element-plus/icons-vue'

const router = useRouter()
const { t } = useI18n()
const userStore = useUserStore()
const appStore = useAppStore()

const currentLanguage = computed(() => appStore.language)

const cards = ref([
  { type: 'ai', icon: MagicStick, titleKey: 'home.aiCaseGeneration', descKey: 'home.aiCaseGenerationDesc' },
  { type: 'api', icon: Link, titleKey: 'home.apiTesting', descKey: 'home.apiTestingDesc' },
  { type: 'ui', icon: Monitor, titleKey: 'home.uiAutomation', descKey: 'home.uiAutomationDesc' },
  { type: 'data', icon: DataLine, titleKey: 'home.dataFactory', descKey: 'home.dataFactoryDesc' },
  { type: 'ai-intelligent', icon: Cpu, titleKey: 'home.aiIntelligentMode', descKey: 'home.aiIntelligentModeDesc' },
  { type: 'assistant', icon: ChatDotRound, titleKey: 'home.aiEvaluator', descKey: 'home.aiEvaluatorDesc' },
  { type: 'config', icon: Setting, titleKey: 'home.configCenter', descKey: 'home.configCenterDesc' },
])

const handleLanguageChange = (lang) => {
  appStore.setLanguage(lang)
}

const handleCommand = (command) => {
  if (command === 'logout') {
    handleLogout()
  }
}

const handleLogout = () => {
  ElMessageBox.confirm(t('home.logoutConfirm'), t('common.tips'), {
    confirmButtonText: t('common.confirm'),
    cancelButtonText: t('common.cancel'),
    type: 'warning',
  })
    .then(() => {
      userStore.logout()
      router.push('/login')
      ElMessage.success(t('home.logoutSuccess'))
    })
    .catch(() => {})
}

const handleNavigate = (type) => {
  const routes = {
    ai: '/ai-generation/requirement-analysis',
    api: '/api-testing/dashboard',
    ui: '/ui-automation/dashboard',
    'ai-intelligent': '/ai-intelligent-mode/testing',
    assistant: '/ai-generation/assistant',
    config: '/configuration/ai-model',
    data: '/data-factory',
  }
  if (routes[type]) {
    const routeData = router.resolve({ path: routes[type] })
    window.open(routeData.href, '_blank')
  }
}
</script>

<style scoped lang="scss">
/* ===== Variables ===== */
$primary: #6366f1;
$primary-light: #818cf8;
$surface: rgba(255, 255, 255, 0.6);
$surface-hover: rgba(255, 255, 255, 0.85);
$text-primary: #1e1b4b;
$text-secondary: #6b7280;
$radius: 20px;
$transition: 0.35s cubic-bezier(0.4, 0, 0.2, 1);

/* ===== Background ===== */
.home-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #eef2ff 0%, #e0e7ff 25%, #f0fdf4 50%, #ede9fe 75%, #fdf2f8 100%);
  background-size: 400% 400%;
  animation: gradientShift 15s ease infinite;
  position: relative;
  overflow: hidden;
}

@keyframes gradientShift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

/* Floating particles */
.bg-particles {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.particle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.15;
  animation: float 20s ease-in-out infinite;

  &.p1 { width: 300px; height: 300px; background: #6366f1; top: -5%; left: -5%; animation-delay: 0s; }
  &.p2 { width: 200px; height: 200px; background: #8b5cf6; top: 60%; right: -3%; animation-delay: -5s; }
  &.p3 { width: 150px; height: 150px; background: #06b6d4; bottom: 10%; left: 20%; animation-delay: -10s; }
  &.p4 { width: 100px; height: 100px; background: #f59e0b; top: 30%; left: 60%; animation-delay: -7s; }
  &.p5 { width: 180px; height: 180px; background: #10b981; top: 10%; right: 25%; animation-delay: -3s; }
  &.p6 { width: 120px; height: 120px; background: #ec4899; bottom: 20%; right: 15%; animation-delay: -12s; }
}

@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(30px, -30px) scale(1.05); }
  50% { transform: translate(-20px, 20px) scale(0.95); }
  75% { transform: translate(15px, 10px) scale(1.02); }
}

/* ===== Layout ===== */
.content-wrapper {
  position: relative;
  z-index: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 32px 60px;
}

/* ===== Top bar ===== */
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 0;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;

  .logo-icon {
    width: 36px;
    height: 36px;

    svg {
      width: 100%;
      height: 100%;
    }
  }

  .logo-text {
    font-size: 20px;
    font-weight: 700;
    color: $text-primary;
    letter-spacing: -0.5px;
  }
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 10px;
  cursor: pointer;
  color: $text-secondary;
  font-size: 14px;
  transition: $transition;
  outline: none;

  &:hover {
    background: $surface;
    color: $primary;
  }
}

.lang-flag {
  font-size: 11px;
  font-weight: 700;
  background: linear-gradient(135deg, $primary, $primary-light);
  color: #fff;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1;
}

.user-btn {
  .user-avatar {
    background: linear-gradient(135deg, $primary, $primary-light);
  }
}

.username {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===== Hero ===== */
.hero {
  text-align: center;
  padding: 48px 0 40px;
  animation: fadeInUp 0.6s ease both;
}

.hero-title {
  font-size: 3rem;
  font-weight: 800;
  color: $text-primary;
  line-height: 1.2;
  margin: 0 0 16px;
  letter-spacing: -1px;

  .title-line {
    background: linear-gradient(135deg, #4f46e5, #7c3aed, #2563eb);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
}

.hero-desc {
  font-size: 1.1rem;
  color: $text-secondary;
  margin: 0;
  font-weight: 400;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(24px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ===== Cards grid ===== */
.cards-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

/* ===== Feature card ===== */
.feature-card {
  position: relative;
  border-radius: $radius;
  cursor: pointer;
  animation: cardIn 0.5s ease both;
  animation-delay: var(--delay);
  overflow: hidden;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.5);
  background: $surface;
  transition: $transition;

  &:hover {
    transform: translateY(-6px);
    background: $surface-hover;
    border-color: rgba(99, 102, 241, 0.2);
    box-shadow: 0 20px 40px -12px rgba(99, 102, 241, 0.15),
                0 8px 16px -8px rgba(0, 0, 0, 0.06);

    .card-glow {
      opacity: 1;
    }

    .icon-wrapper {
      transform: scale(1.08) rotate(-3deg);
    }

    .card-arrow {
      opacity: 1;
      transform: translateX(0);
    }
  }

  &:active {
    transform: translateY(-2px) scale(0.98);
  }
}

.card-glow {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  opacity: 0;
  transition: opacity 0.5s;
  pointer-events: none;
}

.card-ai .card-glow { background: radial-gradient(circle at 30% 30%, rgba(99, 102, 241, 0.08), transparent 60%); }
.card-api .card-glow { background: radial-gradient(circle at 30% 30%, rgba(16, 185, 129, 0.08), transparent 60%); }
.card-ui .card-glow { background: radial-gradient(circle at 30% 30%, rgba(245, 158, 11, 0.08), transparent 60%); }
.card-data .card-glow { background: radial-gradient(circle at 30% 30%, rgba(6, 182, 212, 0.08), transparent 60%); }
.card-ai-intelligent .card-glow { background: radial-gradient(circle at 30% 30%, rgba(139, 92, 246, 0.08), transparent 60%); }
.card-assistant .card-glow { background: radial-gradient(circle at 30% 30%, rgba(236, 72, 153, 0.08), transparent 60%); }
.card-config .card-glow { background: radial-gradient(circle at 30% 30%, rgba(107, 114, 128, 0.08), transparent 60%); }

.card-body {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px;
}

.icon-wrapper {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  transition: $transition;

  &.icon-ai {
    background: linear-gradient(135deg, #eef2ff, #e0e7ff);
    color: #6366f1;
  }
  &.icon-api {
    background: linear-gradient(135deg, #ecfdf5, #d1fae5);
    color: #10b981;
  }
  &.icon-ui {
    background: linear-gradient(135deg, #fffbeb, #fef3c7);
    color: #f59e0b;
  }
  &.icon-data {
    background: linear-gradient(135deg, #ecfeff, #cffafe);
    color: #06b6d4;
  }
  &.icon-ai-intelligent {
    background: linear-gradient(135deg, #f5f3ff, #ede9fe);
    color: #8b5cf6;
  }
  &.icon-assistant {
    background: linear-gradient(135deg, #fdf2f8, #fce7f3);
    color: #ec4899;
  }
  &.icon-config {
    background: linear-gradient(135deg, #f9fafb, #f3f4f6);
    color: #6b7280;
  }
}

.card-text {
  flex: 1;
  min-width: 0;

  h3 {
    font-size: 1rem;
    font-weight: 650;
    color: $text-primary;
    margin: 0 0 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  p {
    font-size: 0.8rem;
    color: $text-secondary;
    margin: 0;
    line-height: 1.4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.card-arrow {
  flex-shrink: 0;
  opacity: 0;
  transform: translateX(-8px);
  transition: $transition;
  color: $primary;
  font-size: 18px;
}

@keyframes cardIn {
  from { opacity: 0; transform: translateY(20px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

/* ===== Responsive ===== */
@media screen and (max-width: 1200px) {
  .cards-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media screen and (max-width: 900px) {
  .cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .hero-title {
    font-size: 2.4rem;
  }

  .hero {
    padding: 36px 0 32px;
  }
}

@media screen and (max-width: 640px) {
  .content-wrapper {
    padding: 0 16px 40px;
  }

  .hero-title {
    font-size: 1.8rem;
  }

  .hero-desc {
    font-size: 0.95rem;
  }

  .cards-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .card-body {
    padding: 18px;
  }

  .icon-wrapper {
    width: 44px;
    height: 44px;
    font-size: 20px;
    border-radius: 12px;
  }

  .username {
    display: none;
  }

  .lang-label {
    display: none;
  }
}
</style>
