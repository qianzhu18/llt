<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()

const dashboard = ref<any>(null)
const loading = ref(true)
const signinMessage = ref('')

async function fetchDashboard() {
  loading.value = true
  try {
    const { data } = await client.get('/me')
    dashboard.value = data
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

async function doSignin() {
  signinMessage.value = ''
  try {
    const { data } = await client.post('/me/signin')
    signinMessage.value = data.message || '签到成功'
    await fetchDashboard()
  } catch (err: any) {
    signinMessage.value = err.response?.data?.detail || '签到失败'
  }
}

onMounted(fetchDashboard)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">个人中心</h1>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else-if="dashboard" class="space-y-6">
      <!-- Profile + Points -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="card">
          <div class="flex items-center gap-4 mb-4">
            <div class="w-16 h-16 rounded-full bg-primary-50 flex items-center justify-center">
              <span class="icon text-3xl text-primary">person</span>
            </div>
            <div>
              <h2 class="font-display font-bold text-lg">{{ auth.user?.nickname }}</h2>
              <p class="text-sm text-gray-500">{{ auth.user?.email }}</p>
            </div>
          </div>
          <div class="flex gap-3">
            <router-link to="/me/profile" class="btn-secondary text-sm">编辑资料</router-link>
            <router-link to="/requests/new" class="btn-primary text-sm">发布求助</router-link>
          </div>
        </div>
        <div class="card">
          <div class="flex items-center justify-between mb-4">
            <div>
              <p class="text-sm text-gray-500">积分余额</p>
              <p class="text-3xl font-bold text-primary">{{ dashboard.points }}</p>
            </div>
            <button @click="doSignin" class="btn-primary">
              <span class="icon mr-1">calendar_today</span>签到
            </button>
          </div>
          <p v-if="signinMessage" class="text-sm text-primary">{{ signinMessage }}</p>
        </div>
      </div>

      <!-- Stats -->
      <div class="grid grid-cols-3 gap-4">
        <div class="card text-center">
          <div class="text-2xl font-bold text-primary">{{ dashboard.my_requests_count }}</div>
          <div class="text-sm text-gray-500">我的求助</div>
        </div>
        <div class="card text-center">
          <div class="text-2xl font-bold text-primary">{{ dashboard.my_helps_count }}</div>
          <div class="text-sm text-gray-500">我的应助</div>
        </div>
        <div class="card text-center">
          <div class="text-2xl font-bold text-primary">{{ dashboard.tx_count }}</div>
          <div class="text-sm text-gray-500">积分记录</div>
        </div>
      </div>

      <!-- Transactions -->
      <div v-if="dashboard.transactions?.length" class="card">
        <h3 class="font-display font-bold mb-4">积分明细</h3>
        <div class="space-y-3">
          <div
            v-for="tx in dashboard.transactions"
            :key="tx.id"
            class="flex items-center justify-between py-2 border-b border-outline-variant/20 last:border-0"
          >
            <div class="flex items-center gap-3">
              <span class="icon text-xl" :class="tx.delta > 0 ? 'text-green-600' : 'text-red-500'">
                {{ tx.delta > 0 ? 'add_circle' : 'remove_circle' }}
              </span>
              <div>
                <p class="text-sm font-medium">{{ tx.reason_label }}</p>
                <p v-if="tx.note" class="text-xs text-gray-400">{{ tx.note }}</p>
              </div>
            </div>
            <span class="font-bold" :class="tx.delta > 0 ? 'text-green-600' : 'text-red-500'">
              {{ tx.delta > 0 ? '+' : '' }}{{ tx.delta }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
