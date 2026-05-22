<script setup lang="ts">
import { useAuthStore } from '../stores/auth'
import { useRouter, useRoute } from 'vue-router'
import { computed } from 'vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const navLinks = computed(() => [
  { name: '首页', to: '/', icon: 'home' },
  { name: '求助大厅', to: '/requests', icon: 'record_voice_over' },
  { name: '共享文库', to: '/library', icon: 'local_library' },
])

const isActive = (path: string) => {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

async function handleLogout() {
  await auth.logout()
  router.push('/')
}
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <!-- Desktop top nav -->
    <header class="hidden md:block bg-white border-b border-outline-variant/30 sticky top-0 z-50">
      <nav class="max-w-container-max mx-auto px-gutter h-16 flex items-center justify-between">
        <div class="flex items-center gap-8">
          <router-link to="/" class="font-display text-xl font-bold text-primary">
            公益文献互助
          </router-link>
          <div class="flex items-center gap-1">
            <router-link
              v-for="link in navLinks"
              :key="link.to"
              :to="link.to"
              class="px-3 py-2 text-sm font-medium rounded-md3 transition-colors"
              :class="isActive(link.to) ? 'text-primary font-bold border-b-2 border-primary' : 'text-gray-600 hover:text-primary hover:bg-primary-50'"
            >
              {{ link.name }}
            </router-link>
            <router-link
              v-if="auth.isAdmin"
              to="/admin"
              class="px-3 py-2 text-sm font-medium rounded-md3 transition-colors"
              :class="isActive('/admin') ? 'text-primary font-bold border-b-2 border-primary' : 'text-gray-600 hover:text-primary hover:bg-primary-50'"
            >
              管理后台
            </router-link>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <template v-if="auth.isLoggedIn">
            <router-link
              to="/me"
              class="px-3 py-2 text-sm font-medium rounded-md3 transition-colors"
              :class="isActive('/me') ? 'text-primary font-bold' : 'text-gray-600 hover:text-primary hover:bg-primary-50'"
            >
              {{ auth.user?.nickname }}
            </router-link>
            <button @click="handleLogout" class="btn-text text-sm">
              退出
            </button>
          </template>
          <template v-else>
            <router-link to="/login" class="btn-text text-sm">登录</router-link>
            <router-link to="/register" class="btn-primary text-sm">注册</router-link>
          </template>
        </div>
      </nav>
    </header>

    <!-- Mobile top bar -->
    <header class="md:hidden bg-white border-b border-outline-variant/30 sticky top-0 z-50">
      <div class="px-4 h-12 flex items-center justify-between">
        <router-link to="/" class="font-display text-lg font-bold text-primary">
          公益文献互助
        </router-link>
        <div class="flex items-center gap-2">
          <template v-if="auth.isLoggedIn">
            <span class="text-sm text-gray-600">{{ auth.user?.nickname }}</span>
          </template>
          <template v-else>
            <router-link to="/login" class="text-sm text-primary font-medium">登录</router-link>
          </template>
        </div>
      </div>
    </header>

    <!-- Main content -->
    <main class="flex-1">
      <slot />
    </main>

    <!-- Mobile bottom tab bar -->
    <nav class="md:hidden fixed bottom-0 inset-x-0 bg-white border-t border-outline-variant/30 z-50">
      <div class="flex">
        <router-link
          v-for="link in navLinks"
          :key="link.to"
          :to="link.to"
          class="flex-1 flex flex-col items-center py-2 text-xs transition-colors"
          :class="isActive(link.to) ? 'text-primary' : 'text-gray-500'"
        >
          <span class="icon text-xl" :class="isActive(link.to) ? '' : ''">{{ link.icon }}</span>
          <span class="mt-0.5">{{ link.name }}</span>
        </router-link>
        <router-link
          v-if="auth.isLoggedIn"
          to="/me"
          class="flex-1 flex flex-col items-center py-2 text-xs transition-colors"
          :class="isActive('/me') ? 'text-primary' : 'text-gray-500'"
        >
          <span class="icon text-xl">person</span>
          <span class="mt-0.5">我的</span>
        </router-link>
        <router-link
          v-else
          to="/login"
          class="flex-1 flex flex-col items-center py-2 text-xs transition-colors"
          :class="isActive('/login') ? 'text-primary' : 'text-gray-500'"
        >
          <span class="icon text-xl">login</span>
          <span class="mt-0.5">登录</span>
        </router-link>
      </div>
    </nav>

    <!-- Mobile bottom spacer -->
    <div class="md:hidden h-16" />
  </div>
</template>
