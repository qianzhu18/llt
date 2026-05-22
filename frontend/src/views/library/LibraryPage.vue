<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import client from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const auth = useAuthStore()

interface Paper {
  id: number
  title: string
  authors: string
  journal: string
  year: number
  download_count: number
}

const papers = ref<Paper[]>([])
const query = ref((route.query.q as string) || '')
const page = ref(Number(route.query.page) || 1)
const totalPages = ref(1)
const loading = ref(true)

async function fetchLibrary() {
  loading.value = true
  try {
    const { data } = await client.get('/library', {
      params: { q: query.value || undefined, page: page.value },
    })
    papers.value = data.items
    totalPages.value = data.total_pages
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

function doSearch() {
  page.value = 1
  fetchLibrary()
}

function goToPage(p: number) {
  page.value = p
  fetchLibrary()
}

function download(id: number) {
  window.open(`/api/v1/library/${id}/download`, '_blank')
}

onMounted(fetchLibrary)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">共享文库</h1>

    <!-- Search -->
    <form @submit.prevent="doSearch" class="mb-8">
      <div class="flex gap-3">
        <input v-model="query" type="text" class="input flex-1" placeholder="搜索标题、作者、期刊..." />
        <button type="submit" class="btn-primary">
          <span class="icon">search</span>
        </button>
      </div>
    </form>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else-if="papers.length === 0" class="text-center py-20 text-gray-500">
      <span class="icon text-5xl text-gray-300 mb-4 block">library_books</span>
      <p>暂无文献</p>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div v-for="paper in papers" :key="paper.id" class="card hover:shadow-md transition-shadow">
        <h3 class="font-display font-bold text-base mb-2 line-clamp-2">{{ paper.title }}</h3>
        <p class="text-sm text-gray-600 mb-1">{{ paper.authors }}</p>
        <p class="text-sm text-gray-500 mb-3">{{ paper.journal }} · {{ paper.year }}</p>
        <div class="flex items-center justify-between">
          <span class="text-xs text-gray-400">
            <span class="icon text-sm align-middle">download</span>
            {{ paper.download_count }} 次
          </span>
          <button v-if="auth.isLoggedIn" @click="download(paper.id)" class="btn-primary text-sm py-1.5 px-3">
            下载
          </button>
          <router-link v-else to="/login" class="text-sm text-primary">登录后下载</router-link>
        </div>
      </div>
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
