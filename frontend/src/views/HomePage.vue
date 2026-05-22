<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '../api/client'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

interface Activity {
  actor: string
  verb: string
  object: string
  ts: string
}

interface LibraryPaper {
  id: number
  title: string
  authors: string
  journal: string
  year: number
  download_count: number
}

const activities = ref<Activity[]>([])
const recentLibrary = ref<LibraryPaper[]>([])
const libraryCount = ref(0)
const searchQuery = ref('')
const searchResults = ref<any>(null)
const searching = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | null = null

async function fetchHome() {
  try {
    const { data } = await client.get('/home')
    activities.value = data.activities
    recentLibrary.value = data.recent_library
    libraryCount.value = data.library_count
  } catch {
    // silent
  }
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) {
    searchResults.value = null
    return
  }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      const { data } = await client.get('/search', { params: { q: searchQuery.value } })
      searchResults.value = data
    } catch {
      searchResults.value = null
    } finally {
      searching.value = false
    }
  }, 300)
}

onMounted(fetchHome)
</script>

<template>
  <div>
    <!-- Hero -->
    <section class="bg-gradient-to-br from-primary-50 to-primary-100 py-16 md:py-24">
      <div class="max-w-container-max mx-auto px-gutter text-center">
        <h1 class="font-display text-3xl md:text-5xl font-bold text-primary-900 mb-4 animate-fade-in-up">
          公益文献互助
        </h1>
        <p class="text-lg md:text-xl text-secondary-700 mb-8 animate-fade-in-up delay-100">
          输入标题、作者、年份，全社区帮你找全文
        </p>

        <!-- Search box -->
        <div class="max-w-2xl mx-auto mb-8 animate-fade-in-up delay-200">
          <div class="relative">
            <span class="icon absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">search</span>
            <input
              v-model="searchQuery"
              @input="onSearchInput"
              type="text"
              placeholder="搜索文献标题、作者、期刊..."
              class="input pl-12 py-4 text-base shadow-md"
            />
            <div v-if="searching" class="absolute right-4 top-1/2 -translate-y-1/2">
              <div class="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          </div>

          <!-- Search results dropdown -->
          <div
            v-if="searchResults"
            class="absolute z-10 mt-2 w-full max-w-2xl left-1/2 -translate-x-1/2 bg-white rounded-md3-lg shadow-lg border border-outline-variant/30 max-h-96 overflow-y-auto"
          >
            <div v-if="searchResults.library_results?.length" class="p-4">
              <h3 class="text-sm font-medium text-gray-500 mb-2">共享文库</h3>
              <router-link
                v-for="paper in searchResults.library_results"
                :key="paper.id"
                :to="`/library`"
                class="block p-3 rounded-md3 hover:bg-surface-container transition-colors"
              >
                <p class="font-medium text-gray-900">{{ paper.title }}</p>
                <p class="text-sm text-gray-500">{{ paper.authors }} · {{ paper.journal }} · {{ paper.year }}</p>
              </router-link>
            </div>
            <div v-if="searchResults.open_req_results?.length" class="p-4 border-t border-outline-variant/30">
              <h3 class="text-sm font-medium text-gray-500 mb-2">开放求助</h3>
              <router-link
                v-for="req in searchResults.open_req_results"
                :key="req.id"
                :to="`/requests/${req.id}`"
                class="block p-3 rounded-md3 hover:bg-surface-container transition-colors"
              >
                <p class="font-medium text-gray-900">{{ req.title }}</p>
                <p class="text-sm text-gray-500">{{ req.authors }} · {{ req.year }}</p>
              </router-link>
            </div>
            <div
              v-if="!searchResults.library_results?.length && !searchResults.open_req_results?.length"
              class="p-8 text-center text-gray-500"
            >
              <span class="icon text-4xl text-gray-300 mb-2">search_off</span>
              <p>没有找到相关结果</p>
              <router-link v-if="auth.isLoggedIn" to="/requests/new" class="text-primary text-sm mt-2 inline-block">
                发布求助 →
              </router-link>
            </div>
          </div>
        </div>

        <!-- CTA buttons -->
        <div class="flex flex-wrap justify-center gap-4 animate-fade-in-up delay-300">
          <router-link v-if="auth.isLoggedIn" to="/requests/new" class="btn-primary">
            <span class="icon mr-2">add_circle</span>发布求助
          </router-link>
          <router-link v-else to="/register" class="btn-primary">
            <span class="icon mr-2">person_add</span>立即注册
          </router-link>
          <router-link to="/requests" class="btn-secondary">
            <span class="icon mr-2">record_voice_over</span>进入求助大厅
          </router-link>
        </div>
      </div>
    </section>

    <!-- How it works -->
    <section class="py-16 bg-white">
      <div class="max-w-container-max mx-auto px-gutter">
        <h2 class="font-display text-2xl font-bold text-center mb-12">四步完成互助</h2>
        <div class="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div v-for="(step, i) in [
            { icon: 'edit_note', title: '发布求助', desc: '填写文献信息，设定积分奖励' },
            { icon: 'handshake', title: '社区接单', desc: '有全文的用户主动接单帮助' },
            { icon: 'verified', title: '确认收货', desc: '确认收到正确文献，积分自动转移' },
            { icon: 'library_books', title: '共享文库', desc: '完成的文献自动进入公共文库' },
          ]" :key="i" class="text-center">
            <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-primary-50 flex items-center justify-center">
              <span class="icon text-3xl text-primary">{{ step.icon }}</span>
            </div>
            <h3 class="font-display font-bold text-lg mb-2">{{ step.title }}</h3>
            <p class="text-gray-600 text-sm">{{ step.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Stats -->
    <section class="py-12 bg-surface-container-low">
      <div class="max-w-container-max mx-auto px-gutter">
        <div class="grid grid-cols-3 gap-4 text-center">
          <div>
            <div class="text-3xl font-bold text-primary">{{ libraryCount }}</div>
            <div class="text-sm text-gray-500">共享文献</div>
          </div>
          <div>
            <div class="text-3xl font-bold text-primary">{{ activities.length }}</div>
            <div class="text-sm text-gray-500">近期动态</div>
          </div>
          <div>
            <div class="text-3xl font-bold text-primary">{{ auth.isLoggedIn ? '已登录' : '未登录' }}</div>
            <div class="text-sm text-gray-500">当前状态</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Activity feed -->
    <section v-if="activities.length" class="py-12 bg-white">
      <div class="max-w-container-max mx-auto px-gutter">
        <h2 class="font-display text-2xl font-bold mb-8">最新动态</h2>
        <div class="space-y-3">
          <div
            v-for="(act, i) in activities"
            :key="i"
            class="flex items-center gap-3 p-3 rounded-md3 bg-surface-container-low"
          >
            <span class="icon text-primary text-xl">
              {{ act.verb === '求助了' ? 'edit_note' : 'check_circle' }}
            </span>
            <div class="flex-1 min-w-0">
              <span class="font-medium">{{ act.actor }}</span>
              <span class="text-gray-500">{{ act.verb }}</span>
              <span v-if="act.object" class="font-medium text-primary truncate">{{ act.object }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Recent library -->
    <section v-if="recentLibrary.length" class="py-12 bg-surface-container-low">
      <div class="max-w-container-max mx-auto px-gutter">
        <div class="flex items-center justify-between mb-8">
          <h2 class="font-display text-2xl font-bold">最新共享文献</h2>
          <router-link to="/library" class="text-primary text-sm font-medium hover:underline">
            查看全部 →
          </router-link>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="paper in recentLibrary"
            :key="paper.id"
            class="card hover:shadow-md transition-shadow reveal-on-scroll"
          >
            <h3 class="font-display font-bold text-base mb-2 line-clamp-2">{{ paper.title }}</h3>
            <p class="text-sm text-gray-600 mb-1">{{ paper.authors }}</p>
            <p class="text-sm text-gray-500 mb-3">{{ paper.journal }} · {{ paper.year }}</p>
            <div class="flex items-center justify-between">
              <span class="text-xs text-gray-400">
                <span class="icon text-sm align-middle">download</span>
                {{ paper.download_count }} 次下载
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.animate-fade-in-up {
  animation: fadeInUp 0.6s ease-out both;
}
.delay-100 { animation-delay: 100ms; }
.delay-200 { animation-delay: 200ms; }
.delay-300 { animation-delay: 300ms; }

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
