<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '../../api/client'

interface ReqItem {
  id: number
  title: string
  status: string
  bounty: number
  requester_nickname: string
  requester_email: string
  created_at: string
}

const requests = ref<ReqItem[]>([])
const statusFilter = ref('')
const page = ref(1)
const totalPages = ref(1)
const loading = ref(true)

const statusLabels: Record<string, string> = {
  '': '全部',
  open: '待应助',
  claimed: '已认领',
  awaiting_confirm: '待确认',
  completed: '已完结',
  closed: '已关闭',
  expired: '已过期',
}

async function fetchRequests() {
  loading.value = true
  try {
    const { data } = await client.get('/admin/requests', {
      params: { status: statusFilter.value || undefined, page: page.value },
    })
    requests.value = data.items
    totalPages.value = data.total_pages
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function filterByStatus(s: string) {
  statusFilter.value = s
  page.value = 1
  fetchRequests()
}

async function forceClose(id: number) {
  if (!confirm('确定强制关闭此请求？积分将退还。')) return
  try {
    await client.post(`/admin/requests/${id}/close`, { note: 'admin 关闭' })
    await fetchRequests()
  } catch {
    // silent
  }
}

onMounted(fetchRequests)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">管理后台</h1>
    <div class="flex gap-2 mb-8 overflow-x-auto pb-2">
      <router-link to="/admin" class="btn-secondary text-sm whitespace-nowrap">概览</router-link>
      <router-link to="/admin/settings" class="btn-secondary text-sm whitespace-nowrap">运行时设置</router-link>
      <router-link to="/admin/gift" class="btn-secondary text-sm whitespace-nowrap">积分赠送</router-link>
      <router-link to="/admin/users" class="btn-secondary text-sm whitespace-nowrap">用户管理</router-link>
      <router-link to="/admin/requests" class="btn-primary text-sm whitespace-nowrap">请求管理</router-link>
      <router-link to="/admin/reports" class="btn-secondary text-sm whitespace-nowrap">举报管理</router-link>
    </div>

    <!-- Status filter -->
    <div class="flex gap-2 mb-6 overflow-x-auto pb-2">
      <button
        v-for="(label, key) in statusLabels" :key="key"
        @click="filterByStatus(key)"
        class="px-3 py-1.5 rounded-md3 text-sm font-medium whitespace-nowrap transition-colors"
        :class="statusFilter === key ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-primary-50 border border-outline-variant'"
      >{{ label }}</button>
    </div>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-outline-variant/30 text-left text-gray-500">
            <th class="py-3 px-2">ID</th>
            <th class="py-3 px-2">标题</th>
            <th class="py-3 px-2">发起人</th>
            <th class="py-3 px-2 text-right">积分</th>
            <th class="py-3 px-2">状态</th>
            <th class="py-3 px-2">创建时间</th>
            <th class="py-3 px-2">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in requests" :key="r.id" class="border-b border-outline-variant/10">
            <td class="py-3 px-2">{{ r.id }}</td>
            <td class="py-3 px-2 max-w-xs truncate">{{ r.title }}</td>
            <td class="py-3 px-2">{{ r.requester_nickname }}</td>
            <td class="py-3 px-2 text-right font-mono">{{ r.bounty }}</td>
            <td class="py-3 px-2">
              <span :class="`badge-${r.status === 'awaiting_confirm' ? 'awaiting' : r.status}`">
                {{ statusLabels[r.status] || r.status }}
              </span>
            </td>
            <td class="py-3 px-2 text-gray-500">{{ r.created_at?.split('T')[0] }}</td>
            <td class="py-3 px-2">
              <button
                v-if="!['completed', 'closed', 'expired'].includes(r.status)"
                @click="forceClose(r.id)"
                class="text-sm text-error hover:underline"
              >关闭</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="totalPages > 1" class="flex justify-center gap-2 mt-8">
      <button
        v-for="p in totalPages" :key="p"
        @click="page = p; fetchRequests()"
        class="w-10 h-10 rounded-md3 text-sm font-medium"
        :class="p === page ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-primary-50 border border-outline-variant'"
      >{{ p }}</button>
    </div>
  </div>
</template>
