<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import client from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const nickname = ref('')
const error = ref('')
const success = ref(false)
const loading = ref(false)

onMounted(() => {
  nickname.value = auth.user?.nickname || ''
})

async function handleSave() {
  error.value = ''
  success.value = false
  loading.value = true
  try {
    await client.post('/me/profile', { nickname: nickname.value })
    success.value = true
    await auth.fetchMe()
  } catch (err: any) {
    error.value = err.response?.data?.detail || '保存失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="max-w-lg mx-auto px-gutter py-8">
    <button @click="router.push('/me')" class="btn-text mb-4 text-sm">
      <span class="icon mr-1">arrow_back</span>返回个人中心
    </button>

    <div class="card">
      <h1 class="font-display text-xl font-bold mb-6">编辑资料</h1>

      <div v-if="error" class="mb-4 p-3 rounded-md3 bg-error-container text-error text-sm">
        {{ error }}
      </div>
      <div v-if="success" class="mb-4 p-3 rounded-md3 bg-green-50 text-green-700 text-sm">
        保存成功
      </div>

      <form @submit.prevent="handleSave" class="space-y-5">
        <div>
          <label class="label">邮箱</label>
          <input :value="auth.user?.email" type="email" class="input bg-gray-50" disabled />
        </div>
        <div>
          <label class="label">昵称</label>
          <input v-model="nickname" type="text" required class="input" />
        </div>
        <button type="submit" class="btn-primary w-full" :disabled="loading">
          <span v-if="loading" class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
          保存
        </button>
      </form>
    </div>
  </div>
</template>
