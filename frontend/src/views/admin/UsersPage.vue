<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '../../api/client'

interface UserItem {
  id: number
  email: string
  nickname: string
  points: number
  is_admin: boolean
  is_active: boolean
  created_at: string
}

const users = ref<UserItem[]>([])
const query = ref('')
const page = ref(1)
const totalPages = ref(1)
const loading = ref(true)

async function fetchUsers() {
  loading.value = true
  try {
    const { data } = await client.get('/admin/users', {
      params: { q: query.value || undefined, page: page.value },
    })
    users.value = data.items
    totalPages.value = data.total_pages
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function doSearch() {
  page.value = 1
  fetchUsers()
}

async function toggleActive(userId: number) {
  if (!confirm('确定切换该用户的启用状态？')) return
  try {
    await client.post(`/admin/users/${userId}/toggle-active`)
    await fetchUsers()
  } catch {
    // silent
  }
}

onMounted(fetchUsers)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">管理后台</h1>
    <div class="flex gap-2 mb-8 overflow-x-auto pb-2">
      <router-link to="/admin" class="btn-secondary text-sm whitespace-nowrap">概览</router-link>
      <router-link to="/admin/settings" class="btn-secondary text-sm whitespace-nowrap">运行时设置</router-link>
      <router-link to="/admin/gift" class="btn-secondary text-sm whitespace-nowrap">积分赠送</router-link>
      <router-link to="/admin/users" class="btn-primary text-sm whitespace-nowrap">用户管理</router-link>
      <router-link to="/admin/requests" class="btn-secondary text-sm whitespace-nowrap">请求管理</router-link>
      <router-link to="/admin/reports" class="btn-secondary text-sm whitespace-nowrap">举报管理</router-link>
    </div>

    <!-- Search -->
    <form @submit.prevent="doSearch" class="mb-6">
      <div class="flex gap-3">
        <input v-model="query" type="text" class="input flex-1" placeholder="搜索邮箱或昵称..." />
        <button type="submit" class="btn-primary"><span class="icon">search</span></button>
      </div>
    </form>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-outline-variant/30 text-left text-gray-500">
            <th class="py-3 px-2">ID</th>
            <th class="py-3 px-2">邮箱</th>
            <th class="py-3 px-2">昵称</th>
            <th class="py-3 px-2 text-right">积分</th>
            <th class="py-3 px-2">角色</th>
            <th class="py-3 px-2">状态</th>
            <th class="py-3 px-2">注册时间</th>
            <th class="py-3 px-2">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id" class="border-b border-outline-variant/10">
            <td class="py-3 px-2">{{ u.id }}</td>
            <td class="py-3 px-2">{{ u.email }}</td>
            <td class="py-3 px-2">{{ u.nickname }}</td>
            <td class="py-3 px-2 text-right font-mono">{{ u.points }}</td>
            <td class="py-3 px-2">
              <span v-if="u.is_admin" class="badge bg-amber-50 text-amber-700 border border-amber-200">管理员</span>
              <span v-else class="text-gray-400">用户</span>
            </td>
            <td class="py-3 px-2">
              <span :class="u.is_active ? 'text-green-600' : 'text-red-500'">
                {{ u.is_active ? '启用' : '禁用' }}
              </span>
            </td>
            <td class="py-3 px-2 text-gray-500">{{ u.created_at?.split('T')[0] }}</td>
            <td class="py-3 px-2">
              <button @click="toggleActive(u.id)" class="text-sm text-primary hover:underline">
                {{ u.is_active ? '禁用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="totalPages > 1" class="flex justify-center gap-2 mt-8">
      <button
        v-for="p in totalPages" :key="p"
        @click="page = p; fetchUsers()"
        class="w-10 h-10 rounded-md3 text-sm font-medium"
        :class="p === page ? 'bg-primary text-white' : 'bg-white text-gray-600 hover:bg-primary-50 border border-outline-variant'"
      >{{ p }}</button>
    </div>
  </div>
</template>
