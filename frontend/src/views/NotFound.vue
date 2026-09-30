<template>
  <div class="not-found">
    <el-result icon="warning" title="404" :sub-title="$t('common.notFound.description')">
      <template #extra>
        <h3 class="not-found-title">{{ $t("common.notFound.title") }}</h3>
        <el-button type="primary" @click="router.push('/home')">
          {{ $t("common.notFound.backHome") }}
        </el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup>
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}

.not-found-title {
  margin: 0 0 16px;
  font-weight: 500;
}
</style>
