<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const error = ref('')
const showResend = ref(false)
const resendEmail = ref('')
const resendMessage = ref('')

async function handleLogin() {
  error.value = ''
  const result = await auth.login(email.value, password.value)
  if (result.ok) {
    const next = (route.query.next as string) || '/'
    router.push(next)
  } else {
    error.value = result.error
  }
}

async function handleResend() {
  resendMessage.value = ''
  try {
    const { data } = await (await import('../api/client')).default.post('/auth/resend-verify', {
      email: resendEmail.value,
    })
    resendMessage.value = data.message || '已发送，请检查邮箱'
  } catch (err: any) {
    resendMessage.value = err.response?.data?.detail || '发送失败'
  }
}
</script>

<template>
  <div class="min-h-[80vh] flex items-center justify-center py-12 px-4">
    <div class="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-0 rounded-md3-lg overflow-hidden shadow-lg">
      <!-- Left: feature highlights -->
      <div class="hidden md:flex flex-col justify-center p-10 bg-gradient-to-br from-primary-600 to-primary-800 text-white">
        <h2 class="font-display text-3xl font-bold mb-6">欢迎回来</h2>
        <div class="space-y-4">
          <div class="flex items-start gap-3">
            <span class="icon text-2xl">library_books</span>
            <div>
              <h3 class="font-medium">共享文库</h3>
              <p class="text-sm text-primary-100">浏览已完成的文献，免费下载</p>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="icon text-2xl">record_voice_over</span>
            <div>
              <h3 class="font-medium">互助求助</h3>
              <p class="text-sm text-primary-100">发布需求，社区帮你找全文</p>
            </div>
          </div>
          <div class="flex items-start gap-3">
            <span class="icon text-2xl">stars</span>
            <div>
              <h3 class="font-medium">积分系统</h3>
              <p class="text-sm text-primary-100">帮助他人赚取积分，兑换文献</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: login form -->
      <div class="p-8 md:p-10 bg-white">
        <h1 class="font-display text-2xl font-bold mb-6">登录</h1>

        <div v-if="error" class="mb-4 p-3 rounded-md3 bg-error-container text-error text-sm">
          {{ error }}
        </div>

        <form @submit.prevent="handleLogin" class="space-y-5">
          <div>
            <label class="label">邮箱</label>
            <input v-model="email" type="email" required class="input" placeholder="your@email.com" />
          </div>
          <div>
            <label class="label">密码</label>
            <input v-model="password" type="password" required class="input" placeholder="至少 8 位" minlength="8" />
          </div>
          <button type="submit" class="btn-primary w-full" :disabled="auth.loading">
            <span v-if="auth.loading" class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
            登录
          </button>
        </form>

        <div class="mt-6 text-center text-sm text-gray-500">
          还没有账号？
          <router-link to="/register" class="text-primary font-medium hover:underline">立即注册</router-link>
        </div>

        <!-- Resend verification -->
        <div class="mt-6 pt-6 border-t border-outline-variant/30">
          <button @click="showResend = !showResend" class="text-sm text-gray-500 hover:text-primary">
            没有收到验证邮件？
          </button>
          <div v-if="showResend" class="mt-3 space-y-3">
            <input v-model="resendEmail" type="email" class="input" placeholder="输入注册邮箱" />
            <button @click="handleResend" class="btn-secondary w-full text-sm">重新发送</button>
            <p v-if="resendMessage" class="text-sm text-gray-600">{{ resendMessage }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
