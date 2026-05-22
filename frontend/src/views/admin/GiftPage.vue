<script setup lang="ts">
import { ref } from 'vue'
import client from '../../api/client'

const target = ref('')
const delta = ref(0)
const note = ref('')
const message = ref('')
const error = ref('')
const loading = ref(false)

async function handleGift() {
  message.value = ''
  error.value = ''
  loading.value = true
  try {
    const { data } = await client.post('/admin/gift', {
      target: target.value,
      delta: delta.value,
      note: note.value,
    })
    message.value = data.message
    target.value = ''
    delta.value = 0
    note.value = ''
  } catch (err: any) {
    error.value = err.response?.data?.detail || '操作失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">管理后台</h1>
    <div class="flex gap-2 mb-8 overflow-x-auto pb-2">
      <router-link to="/admin" class="btn-secondary text-sm whitespace-nowrap">概览</router-link>
      <router-link to="/admin/settings" class="btn-secondary text-sm whitespace-nowrap">运行时设置</router-link>
      <router-link to="/admin/gift" class="btn-primary text-sm whitespace-nowrap">积分赠送</router-link>
      <router-link to="/admin/users" class="btn-secondary text-sm whitespace-nowrap">用户管理</router-link>
      <router-link to="/admin/requests" class="btn-secondary text-sm whitespace-nowrap">请求管理</router-link>
      <router-link to="/admin/reports" class="btn-secondary text-sm whitespace-nowrap">举报管理</router-link>
    </div>

    <div class="max-w-lg">
      <div class="card">
        <h2 class="font-display font-bold text-lg mb-4">积分赠送 / 扣减</h2>

        <div v-if="message" class="mb-4 p-3 rounded-md3 bg-green-50 text-green-700 text-sm">{{ message }}</div>
        <div v-if="error" class="mb-4 p-3 rounded-md3 bg-error-container text-error text-sm">{{ error }}</div>

        <form @submit.prevent="handleGift" class="space-y-5">
          <div>
            <label class="label">目标用户（邮箱或 ID）</label>
            <input v-model="target" type="text" required class="input" placeholder="user@example.com 或 123" />
          </div>
          <div>
            <label class="label">积分变动（正数=赠送，负数=扣减）</label>
            <input v-model.number="delta" type="number" required class="input" />
          </div>
          <div>
            <label class="label">备注</label>
            <input v-model="note" type="text" class="input" placeholder="可选" />
          </div>
          <button type="submit" class="btn-primary w-full" :disabled="loading">
            <span v-if="loading" class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
            执行
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
