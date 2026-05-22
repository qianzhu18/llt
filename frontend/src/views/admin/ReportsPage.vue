<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '../../api/client'

interface ReportItem {
  id: number
  reason: string
  request_id: number
  request_title: string
  request_status: string
  reporter_email: string
  created_at: string
}

const reports = ref<ReportItem[]>([])
const page = ref(1)
const totalPages = ref(1)
const loading = ref(true)

async function fetchReports() {
  loading.value = true
  try {
    const { data } = await client.get('/admin/reports', { params: { page: page.value } })
    reports.value = data.items
    totalPages.value = data.total_pages
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

async function dismissReport(id: number) {
  if (!confirm('确定驳回此举报？')) return
  try {
    await client.post(`/admin/reports/${id}/dismiss`)
    await fetchReports()
  } catch {
    // silent
  }
}

onMounted(fetchReports)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">管理后台</h1>
    <div class="flex gap-2 mb-8 overflow-x-auto pb-2">
      <router-link to="/admin" class="btn-secondary text-sm whitespace-nowrap">概览</router-link>
      <router-link to="/admin/settings" class="btn-secondary text-sm whitespace-nowrap">运行时设置</router-link>
      <router-link to="/admin/gift" class="btn-secondary text-sm whitespace-nowrap">积分赠送</router-link>
      <router-link to="/admin/users" class="btn-secondary text-sm whitespace-nowrap">用户管理</router-link>
      <router-link to="/admin/requests" class="btn-secondary text-sm whitespace-nowrap">请求管理</router-link>
      <router-link to="/admin/reports" class="btn-primary text-sm whitespace-nowrap">举报管理</router-link>
    </div>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else-if="reports.length === 0" class="text-center py-20 text-gray-500">
      <span class="icon text-5xl text-gray-300 mb-4 block">check_circle</span>
      <p>暂无举报</p>
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-outline-variant/30 text-left text-gray-500">
            <th class="py-3 px-2">时间</th>
            <th class="py-3 px-2">举报人</th>
            <th class="py-3 px-2">关联请求</th>
            <th class="py-3 px-2">请求状态</th>
            <th class="py-3 px-2">原因</th>
            <th class="py-3 px-2">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in reports" :key="r.id" class="border-b border-outline-variant/10">
            <td class="py-3 px-2 text-gray-500">{{ r.created_at?.split('T')[0] }}</td>
            <td class="py-3 px-2">{{ r.reporter_email }}</td>
            <td class="py-3 px-2">
              <router-link :to="`/requests/${r.request_id}`" class="text-primary hover:underline">
                #{{ r.request_id }} {{ r.request_title }}
              </router-link>
            </td>
            <td class="py-3 px-2">{{ r.request_status }}</td>
            <td class="py-3 px-2 max-w-xs truncate">{{ r.reason }}</td>
            <td class="py-3 px-2">
              <button @click="dismissReport(r.id)" class="text-sm text-primary hover:underline">驳回</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="totalPages > 1" class="flex justify-center gap-2 mt-8">
      <button
        v-for="p in totalPages" :key="p"
        @click="page = p; fetchReports()"
        class="w-10 h-10 rounded-md3 text-sm font-medium"
        :class="p === page ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-primary-50 border border-outline-variant'"
      >{{ p }}</button>
    </div>
  </div>
</template>
