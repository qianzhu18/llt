<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '../../api/client'

const stats = ref<any>(null)
const loading = ref(true)

async function fetchStats() {
  loading.value = true
  try {
    const { data } = await client.get('/admin')
    stats.value = data
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

onMounted(fetchStats)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">管理后台</h1>

    <div class="flex gap-2 mb-8 overflow-x-auto pb-2">
      <router-link to="/admin" class="btn-primary text-sm whitespace-nowrap">概览</router-link>
      <router-link to="/admin/settings" class="btn-secondary text-sm whitespace-nowrap">运行时设置</router-link>
      <router-link to="/admin/gift" class="btn-secondary text-sm whitespace-nowrap">积分赠送</router-link>
      <router-link to="/admin/users" class="btn-secondary text-sm whitespace-nowrap">用户管理</router-link>
      <router-link to="/admin/requests" class="btn-secondary text-sm whitespace-nowrap">请求管理</router-link>
      <router-link to="/admin/reports" class="btn-secondary text-sm whitespace-nowrap">举报管理</router-link>
    </div>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="card text-center">
        <div class="text-3xl font-bold text-primary">{{ stats.users }}</div>
        <div class="text-sm text-gray-500">用户总数</div>
      </div>
      <div class="card text-center">
        <div class="text-3xl font-bold text-primary">{{ stats.total_requests }}</div>
        <div class="text-sm text-gray-500">请求总数</div>
      </div>
      <div class="card text-center">
        <div class="text-3xl font-bold text-primary">{{ stats.open_requests }}</div>
        <div class="text-sm text-gray-500">开放请求</div>
      </div>
      <div class="card text-center">
        <div class="text-3xl font-bold text-primary">{{ stats.reports }}</div>
        <div class="text-sm text-gray-500">待处理举报</div>
      </div>
    </div>
  </div>
</template>
