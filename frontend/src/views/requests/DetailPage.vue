<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import client from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const id = route.params.id

const req = ref<any>(null)
const loading = ref(true)
const error = ref('')
const uploading = ref(false)
const rejectReason = ref('')
const reportReason = ref('')
const showReject = ref(false)
const showReport = ref(false)

const statusLabels: Record<string, string> = {
  open: '等待接单',
  claimed: '已接单',
  awaiting_confirm: '待确认',
  completed: '已完成',
  closed: '已关闭',
  expired: '已过期',
}

const viewerRole = computed(() => {
  if (!req.value || !auth.user) return 'visitor'
  if (auth.user.id === req.value.requester_id) return 'owner'
  if (auth.user.id === req.value.claimed_by) return 'helper'
  return 'visitor'
})

async function fetchRequest() {
  loading.value = true
  try {
    const { data } = await client.get(`/requests/${id}`)
    req.value = data
  } catch (err: any) {
    error.value = err.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function doAction(action: string, body?: any) {
  error.value = ''
  try {
    await client.post(`/requests/${id}/${action}`, body)
    await fetchRequest()
  } catch (err: any) {
    error.value = err.response?.data?.detail || '操作失败'
  }
}

async function handleUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  uploading.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('pdf', file)
    await client.post(`/requests/${id}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    await fetchRequest()
  } catch (err: any) {
    error.value = err.response?.data?.detail || '上传失败'
  } finally {
    uploading.value = false
  }
}

function downloadPdf() {
  window.open(`/api/v1/requests/${id}/download`, '_blank')
}

onMounted(fetchRequest)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <button @click="router.back()" class="btn-text mb-4 text-sm">
      <span class="icon mr-1">arrow_back</span>返回
    </button>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else-if="error" class="text-center py-20 text-error">
      {{ error }}
    </div>

    <div v-else-if="req" class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Left: detail -->
      <div class="lg:col-span-2 space-y-6">
        <div class="card">
          <div class="flex items-start justify-between mb-4">
            <span :class="`badge-${req.status === 'awaiting_confirm' ? 'awaiting' : req.status}`">
              {{ statusLabels[req.status] || req.status }}
            </span>
            <span class="text-lg font-bold text-amber-600">{{ req.bounty }} 积分</span>
          </div>
          <h1 class="font-display text-xl font-bold mb-4">{{ req.title }}</h1>
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span class="text-gray-500">作者</span>
              <p class="font-medium">{{ req.authors }}</p>
            </div>
            <div>
              <span class="text-gray-500">年份</span>
              <p class="font-medium">{{ req.year }}</p>
            </div>
            <div v-if="req.journal">
              <span class="text-gray-500">期刊</span>
              <p class="font-medium">{{ req.journal }}</p>
            </div>
            <div>
              <span class="text-gray-500">发起人</span>
              <p class="font-medium">{{ req.requester_nickname }}</p>
            </div>
          </div>
          <div v-if="req.extra" class="mt-4 p-3 rounded-md3 bg-surface-container-low text-sm">
            {{ req.extra }}
          </div>
          <div v-if="req.helper_nickname" class="mt-4 flex items-center gap-2 text-sm text-gray-600">
            <span class="icon text-primary">person</span>
            应助人：{{ req.helper_nickname }}
          </div>
          <div class="mt-4 flex flex-wrap gap-2 text-xs text-gray-400">
            <span class="badge bg-gray-50 text-gray-500 border border-gray-200">
              {{ req.time_remaining }}
            </span>
          </div>
        </div>
      </div>

      <!-- Right: actions -->
      <div class="space-y-4">
        <div class="card sticky top-24">
          <h3 class="font-display font-bold mb-4">操作</h3>

          <!-- Open: visitor can claim -->
          <div v-if="req.status === 'open' && viewerRole === 'visitor' && auth.isLoggedIn">
            <button @click="doAction('claim')" class="btn-primary w-full">
              <span class="icon mr-2">handshake</span>接单帮助
            </button>
          </div>

          <!-- Claimed: helper can upload/release -->
          <div v-if="req.status === 'claimed' && viewerRole === 'helper'" class="space-y-3">
            <label class="btn-primary w-full cursor-pointer text-center">
              <span class="icon mr-2">cloud_upload</span>
              {{ uploading ? '上传中...' : '上传 PDF' }}
              <input type="file" accept=".pdf" class="hidden" @change="handleUpload" :disabled="uploading" />
            </label>
            <button @click="doAction('release')" class="btn-secondary w-full">
              <span class="icon mr-2">undo</span>释放任务
            </button>
          </div>

          <!-- Awaiting confirm: owner can confirm/reject -->
          <div v-if="req.status === 'awaiting_confirm' && viewerRole === 'owner'" class="space-y-3">
            <button @click="doAction('confirm')" class="btn-primary w-full">
              <span class="icon mr-2">check_circle</span>确认收货
            </button>
            <button @click="showReject = !showReject" class="btn-secondary w-full">
              <span class="icon mr-2">replay</span>要求重传
            </button>
            <div v-if="showReject" class="space-y-2">
              <textarea v-model="rejectReason" class="input" rows="2" placeholder="拒绝原因（可选）" />
              <button @click="doAction('reject', { reason: rejectReason })" class="btn-error w-full text-sm">
                确认拒绝
              </button>
            </div>
          </div>

          <!-- Completed: download -->
          <div v-if="req.status === 'completed'" class="space-y-3">
            <button @click="downloadPdf" class="btn-primary w-full">
              <span class="icon mr-2">download</span>下载 PDF
            </button>
          </div>

          <!-- Report -->
          <div v-if="auth.isLoggedIn && req.status !== 'completed' && req.status !== 'closed' && viewerRole !== 'owner'" class="mt-4 pt-4 border-t border-outline-variant/30">
            <button @click="showReport = !showReport" class="text-sm text-gray-500 hover:text-error">
              举报此求助
            </button>
            <div v-if="showReport" class="mt-2 space-y-2">
              <textarea v-model="reportReason" class="input" rows="2" placeholder="举报原因" />
              <button @click="doAction('report', { reason: reportReason })" class="btn-error w-full text-sm">
                提交举报
              </button>
            </div>
          </div>

          <!-- Not logged in -->
          <div v-if="!auth.isLoggedIn" class="text-center text-sm text-gray-500">
            <router-link :to="`/login?next=/requests/${id}`" class="text-primary font-medium">登录</router-link>
            后可操作
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
