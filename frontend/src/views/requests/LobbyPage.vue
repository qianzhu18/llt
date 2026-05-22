<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()

interface HelpRequest {
  id: number
  title: string
  authors: string
  journal: string
  year: number
  bounty: number
  status: string
  requester_nickname: string
  created_at: string
  time_remaining: string
}

const requests = ref<HelpRequest[]>([])
const page = ref(1)
const totalPages = ref(1)
const loading = ref(true)

const statusLabels: Record<string, string> = {
  open: '等待接单',
  claimed: '已接单',
  awaiting_confirm: '待确认',
  completed: '已完成',
  closed: '已关闭',
  expired: '已过期',
}

async function fetchRequests() {
  loading.value = true
  try {
    const { data } = await client.get('/requests', { params: { page: page.value } })
    requests.value = data.items
    totalPages.value = data.total_pages
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function goToPage(p: number) {
  page.value = p
  fetchRequests()
}

onMounted(fetchRequests)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <div class="flex items-center justify-between mb-8">
      <h1 class="font-display text-2xl font-bold">求助大厅</h1>
      <router-link v-if="auth.isLoggedIn" to="/requests/new" class="btn-primary">
        <span class="icon mr-2">add_circle</span>发布求助
      </router-link>
    </div>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else-if="requests.length === 0" class="text-center py-20 text-gray-500">
      <span class="icon text-5xl text-gray-300 mb-4 block">inbox</span>
      <p>暂无求助</p>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <router-link
        v-for="req in requests"
        :key="req.id"
        :to="`/requests/${req.id}`"
        class="card hover:shadow-md transition-all hover:-translate-y-0.5"
      >
        <div class="flex items-start justify-between mb-3">
          <span :class="`badge-${req.status === 'awaiting_confirm' ? 'awaiting' : req.status}`">
            {{ statusLabels[req.status] || req.status }}
          </span>
          <span class="text-sm font-bold text-amber-600">{{ req.bounty }} 积分</span>
        </div>
        <h3 class="font-display font-bold text-base mb-2 line-clamp-2">{{ req.title }}</h3>
        <p class="text-sm text-gray-600 mb-1">{{ req.authors }}</p>
        <p class="text-sm text-gray-500 mb-3">{{ req.journal }} · {{ req.year }}</p>
        <div class="flex items-center justify-between text-xs text-gray-400">
          <span>{{ req.requester_nickname }}</span>
          <span>{{ req.time_remaining }}</span>
        </div>
      </router-link>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex justify-center gap-2 mt-8">
      <button
        v-for="p in totalPages"
        :key="p"
        @click="goToPage(p)"
        class="w-10 h-10 rounded-md3 text-sm font-medium transition-colors"
        :class="p === page ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-primary-50 border border-outline-variant'"
      >
        {{ p }}
      </button>
    </div>

    <!-- Mobile FAB -->
    <router-link
      v-if="auth.isLoggedIn"
      to="/requests/new"
      class="md:hidden fixed bottom-20 right-4 w-14 h-14 rounded-full bg-primary text-white shadow-lg flex items-center justify-center z-40 hover:bg-primary-700 transition-colors"
    >
      <span class="icon text-2xl">add</span>
    </router-link>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
