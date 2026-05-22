<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '../../api/client'

interface SettingKnob {
  key: string
  type: string
  label: string
  help: string
  group: string
  current: string
  default: string
  overridden: boolean
}

const items = ref<SettingKnob[]>([])
const smtp = ref<any>(null)
const loading = ref(true)
const saving = ref(false)
const message = ref('')
const error = ref('')
const testEmail = ref('')
const testMessage = ref('')

const values = ref<Record<string, string>>({})
const toggles = ref<string[]>([])

async function fetchSettings() {
  loading.value = true
  try {
    const { data } = await client.get('/admin/settings')
    items.value = data.items
    smtp.value = data.smtp
    for (const item of data.items) {
      if (item.type === 'bool') {
        if (item.current === true || item.current === 'true') {
          toggles.value.push(item.key)
        }
      } else {
        values.value[item.key] = String(item.current ?? '')
      }
    }
  } catch {
    // silent
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  message.value = ''
  error.value = ''
  try {
    const { data } = await client.post('/admin/settings', {
      values: values.value,
      toggles: toggles.value,
    })
    message.value = `已保存 ${data.changed} 项设置`
    await fetchSettings()
  } catch (err: any) {
    error.value = err.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

async function handleReset(key: string) {
  try {
    await client.post('/admin/settings/reset', { key })
    await fetchSettings()
  } catch {
    // silent
  }
}

async function handleTestEmail() {
  testMessage.value = ''
  try {
    const { data } = await client.post('/admin/settings/test-email', { email: testEmail.value })
    testMessage.value = data.message
  } catch (err: any) {
    testMessage.value = err.response?.data?.detail || '发送失败'
  }
}

function toggleKey(key: string) {
  const idx = toggles.value.indexOf(key)
  if (idx >= 0) toggles.value.splice(idx, 1)
  else toggles.value.push(key)
}

const groups = ['积分 / 时限', '内容 / 安全', '站点文案', '邮件 SMTP']

onMounted(fetchSettings)
</script>

<template>
  <div class="max-w-container-max mx-auto px-gutter py-8">
    <h1 class="font-display text-2xl font-bold mb-6">管理后台</h1>
    <div class="flex gap-2 mb-8 overflow-x-auto pb-2">
      <router-link to="/admin" class="btn-secondary text-sm whitespace-nowrap">概览</router-link>
      <router-link to="/admin/settings" class="btn-primary text-sm whitespace-nowrap">运行时设置</router-link>
      <router-link to="/admin/gift" class="btn-secondary text-sm whitespace-nowrap">积分赠送</router-link>
      <router-link to="/admin/users" class="btn-secondary text-sm whitespace-nowrap">用户管理</router-link>
      <router-link to="/admin/requests" class="btn-secondary text-sm whitespace-nowrap">请求管理</router-link>
      <router-link to="/admin/reports" class="btn-secondary text-sm whitespace-nowrap">举报管理</router-link>
    </div>

    <div v-if="loading" class="text-center py-20">
      <div class="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
    </div>

    <div v-else>
      <!-- SMTP status + test -->
      <div class="card mb-6">
        <h3 class="font-display font-bold mb-3">SMTP 状态</h3>
        <p class="text-sm text-gray-600 mb-3">
          {{ smtp?.configured ? `已配置 (${smtp.host}:${smtp.port})` : '未配置' }}
        </p>
        <div class="flex gap-3">
          <input v-model="testEmail" type="email" class="input flex-1" placeholder="测试收件邮箱" />
          <button @click="handleTestEmail" class="btn-secondary text-sm">发送测试</button>
        </div>
        <p v-if="testMessage" class="text-sm mt-2" :class="testMessage.includes('失败') ? 'text-error' : 'text-green-600'">{{ testMessage }}</p>
      </div>

      <!-- Settings form -->
      <form @submit.prevent="handleSave">
        <div v-for="group in groups" :key="group" class="mb-6">
          <h3 class="font-display font-bold mb-3 text-lg">{{ group }}</h3>
          <div class="card space-y-4">
            <div v-for="item in items.filter(i => i.group === group)" :key="item.key">
              <div class="flex items-center justify-between mb-1">
                <label class="label mb-0">{{ item.label }}</label>
                <button
                  v-if="item.overridden"
                  type="button"
                  @click="handleReset(item.key)"
                  class="text-xs text-gray-400 hover:text-primary"
                >
                  恢复默认
                </button>
              </div>
              <p v-if="item.help" class="text-xs text-gray-400 mb-1.5">{{ item.help }}</p>

              <!-- Bool toggle -->
              <div v-if="item.type === 'bool'" class="flex items-center gap-3">
                <button
                  type="button"
                  @click="toggleKey(item.key)"
                  class="w-12 h-6 rounded-full transition-colors relative"
                  :class="toggles.includes(item.key) ? 'bg-primary' : 'bg-gray-300'"
                >
                  <div
                    class="w-5 h-5 bg-white rounded-full shadow absolute top-0.5 transition-transform"
                    :class="toggles.includes(item.key) ? 'translate-x-6' : 'translate-x-0.5'"
                  />
                </button>
                <span class="text-sm text-gray-500">{{ toggles.includes(item.key) ? '开启' : '关闭' }}</span>
              </div>

              <!-- Password -->
              <input
                v-else-if="item.type === 'password'"
                v-model="values[item.key]"
                type="password"
                class="input"
                :placeholder="`默认: ${item.default || '(空)'}`"
              />

              <!-- Text / Int -->
              <input
                v-else
                v-model="values[item.key]"
                :type="item.type === 'int' ? 'number' : 'text'"
                class="input"
                :placeholder="`默认: ${item.default || '(空)'}`"
              />
            </div>
          </div>
        </div>

        <div v-if="message" class="mb-4 p-3 rounded-md3 bg-green-50 text-green-700 text-sm">{{ message }}</div>
        <div v-if="error" class="mb-4 p-3 rounded-md3 bg-error-container text-error text-sm">{{ error }}</div>

        <button type="submit" class="btn-primary" :disabled="saving">
          <span v-if="saving" class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
          保存全部设置
        </button>
      </form>
    </div>
  </div>
</template>
