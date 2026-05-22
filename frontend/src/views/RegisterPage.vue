<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const email = ref('')
const nickname = ref('')
const password = ref('')
const error = ref('')
const success = ref('')

async function handleRegister() {
  error.value = ''
  success.value = ''
  const result = await auth.register(email.value, nickname.value, password.value)
  if (result.ok) {
    success.value = result.message || '注册成功，请查收验证邮件'
  } else {
    error.value = result.error
  }
}
</script>

<template>
  <div class="min-h-[80vh] flex items-center justify-center py-12 px-4">
    <div class="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-0 rounded-md3-lg overflow-hidden shadow-lg">
      <!-- Left: feature highlights -->
      <div class="hidden md:flex flex-col justify-center p-10 bg-gradient-to-br from-primary-600 to-primary-800 text-white">
        <h2 class="font-display text-3xl font-bold mb-6">加入互助社区</h2>
        <div class="space-y-4">
          <div class="flex items-start gap-3">
            <span class="icon text-2xl">stars</span>
            <div>
              <h3 class="font-medium">积分奖励</h3>
              <p class="text-sm text-primary-100">注册即送积分，每日签到获取更多</p>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="icon text-2xl">group</span>
            <div>
              <h3 class="font-medium">社区互助</h3>
              <p class="text-sm text-primary-100">数千用户共享文献资源</p>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="icon text-2xl">security</span>
            <div>
              <h3 class="font-medium">安全可靠</h3>
              <p class="text-sm text-primary-100">PDF 脱敏处理，保护隐私</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: register form -->
      <div class="p-8 md:p-10 bg-white">
        <h1 class="font-display text-2xl font-bold mb-6">注册</h1>

        <div v-if="error" class="mb-4 p-3 rounded-md3 bg-error-container text-error text-sm">
          {{ error }}
        </div>
        <div v-if="success" class="mb-4 p-3 rounded-md3 bg-green-50 text-green-700 text-sm">
          {{ success }}
          <router-link to="/login" class="font-medium ml-1 underline">去登录</router-link>
        </div>

        <form @submit.prevent="handleRegister" class="space-y-5">
          <div>
            <label class="label">邮箱</label>
            <input v-model="email" type="email" required class="input" placeholder="your@email.com" />
          </div>
          <div>
            <label class="label">昵称</label>
            <input v-model="nickname" type="text" required class="input" placeholder="你的显示名称" />
          </div>
          <div>
            <label class="label">密码</label>
            <input v-model="password" type="password" required class="input" placeholder="至少 8 位" minlength="8" />
          </div>
          <button type="submit" class="btn-primary w-full" :disabled="auth.loading">
            <span v-if="auth.loading" class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
            注册
          </button>
        </form>

        <div class="mt-6 text-center text-sm text-gray-500">
          已有账号？
          <router-link to="/login" class="text-primary font-medium hover:underline">去登录</router-link>
        </div>
      </div>
    </div>
  </div>
</template>
