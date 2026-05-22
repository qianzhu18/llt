<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import client from '../../api/client'

const router = useRouter()

const title = ref('')
const authors = ref('')
const journal = ref('')
const year = ref(new Date().getFullYear())
const extra = ref('')
const bounty = ref(20)
const error = ref('')
const loading = ref(false)
const userPoints = ref(0)
const activeCount = ref(0)
const maxActive = ref(3)

const bountyOptions = [10, 20, 30, 50]

async function fetchInfo() {
  try {
    const { data } = await client.get('/requests/new-info')
    userPoints.value = data.points
    activeCount.value = data.active_count
    maxActive.value = data.max_active
  } catch {
    // silent
  }
}

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    await client.post('/requests', {
      title: title.value,
      authors: authors.value,
      journal: journal.value || null,
      year: year.value,
      extra: extra.value || null,
      bounty: bounty.value,
    })
    router.push('/requests')
  } catch (err: any) {
    error.value = err.response?.data?.detail || '发布失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchInfo)
</script>

<template>
  <div class="max-w-2xl mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">发布求助</h1>

    <!-- Info chips -->
    <div class="flex flex-wrap gap-3 mb-6">
      <div class="badge bg-primary-50 text-primary-700 border border-primary-200">
        当前积分：{{ userPoints }}
      </div>
      <div class="badge bg-blue-50 text-blue-700 border border-blue-200">
        进行中：{{ activeCount }} / {{ maxActive }}
      </div>
    </div>

    <div v-if="error" class="mb-4 p-3 rounded-md3 bg-error-container text-error text-sm">
      {{ error }}
    </div>

    <form @submit.prevent="handleSubmit" class="space-y-5">
      <div>
        <label class="label">文献标题 <span class="text-error">*</span></label>
        <input v-model="title" type="text" required class="input" placeholder="完整的文献标题" />
      </div>
      <div>
        <label class="label">作者 <span class="text-error">*</span></label>
        <input v-model="authors" type="text" required class="input" placeholder="如：Zhang et al." />
      </div>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="label">期刊</label>
          <input v-model="journal" type="text" class="input" placeholder="可选" />
        </div>
        <div>
          <label class="label">年份 <span class="text-error">*</span></label>
          <input v-model.number="year" type="number" required class="input" :max="new Date().getFullYear()" />
        </div>
      </div>
      <div>
        <label class="label">备注</label>
        <textarea v-model="extra" class="input" rows="3" placeholder="补充说明（可选）" />
      </div>
      <div>
        <label class="label">悬赏积分 <span class="text-error">*</span></label>
        <div class="flex gap-3">
          <label
            v-for="opt in bountyOptions"
            :key="opt"
            class="flex-1 cursor-pointer"
          >
            <input type="radio" :value="opt" v-model.number="bounty" class="sr-only peer" />
            <div class="text-center py-3 rounded-md3 border-2 transition-all peer-checked:border-primary peer-checked:bg-primary-50 peer-checked:text-primary border-outline-variant hover:border-primary/50">
              <div class="text-xl font-bold">{{ opt }}</div>
              <div class="text-xs text-gray-500">积分</div>
            </div>
          </label>
        </div>
      </div>
      <button type="submit" class="btn-primary w-full" :disabled="loading || activeCount >= maxActive">
        <span v-if="loading" class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
        发布求助
      </button>
      <p v-if="activeCount >= maxActive" class="text-center text-sm text-error">
        已达到同时进行的最大求助数
      </p>
    </form>
  </div>
</template>
