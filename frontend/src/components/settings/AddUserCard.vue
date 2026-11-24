<template>
  <div class="p-4 rounded-xl bg-[#080d1a] border border-cyan-900/40 relative font-mono text-xs space-y-4">
    <!-- Card Header -->
    <div class="border-b border-gray-800 pb-3">
      <h3 class="text-xs font-bold text-gray-200 uppercase tracking-widest flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
        <span>// {{ t('settings_add_user_card_title') || 'Register New User' }}</span>
      </h3>
      <p class="text-[11px] text-gray-400 mt-0.5">
        {{ t('settings_add_user_card_desc') || 'Register daily operator account or viewer.' }}
      </p>
    </div>

    <!-- Alert / Error Banner -->
    <div v-if="errorMsg" class="p-2 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[11px]">
      {{ errorMsg }}
    </div>

    <form @submit.prevent="handleSubmit" class="space-y-3.5">
      <!-- Username -->
      <div>
        <label class="block text-[11px] font-semibold text-gray-300 uppercase mb-1">
          {{ t('settings_col_username') || 'Username' }} *
        </label>
        <input
          v-model="form.username"
          type="text"
          required
          minlength="3"
          maxlength="50"
          placeholder="e.g. sysops-andi"
          autocomplete="off"
          class="w-full bg-[#111827] border border-gray-800 focus:border-cyan-500 rounded px-3 py-1.5 text-xs text-gray-200 outline-none"
        />
      </div>

      <!-- Password Awal -->
      <div>
        <label class="block text-[11px] font-semibold text-gray-300 uppercase mb-1">
          {{ t('login_password') || 'Initial Password' }} *
        </label>
        <input
          v-model="form.password"
          type="password"
          required
          minlength="8"
          placeholder="Min. 8 characters strong"
          autocomplete="new-password"
          class="w-full bg-[#111827] border border-gray-800 focus:border-cyan-500 rounded px-3 py-1.5 text-xs text-gray-200 outline-none"
        />
        <div class="text-[10px] text-gray-400 mt-1">
          {{ t('settings_pwd_requirement') || 'Min. 8 chars with uppercase, lowercase, and number.' }}
        </div>
      </div>

      <!-- Role / Hak Akses -->
      <div>
        <label class="block text-[11px] font-semibold text-gray-300 uppercase mb-1">
          {{ t('settings_col_role') || 'Role / Authority' }} *
        </label>
        <select
          v-model="form.role"
          class="w-full bg-[#111827] border border-gray-800 focus:border-cyan-500 rounded px-3 py-1.5 text-xs text-gray-200 outline-none cursor-pointer"
        >
          <option value="operator">{{ t('settings_role_operator') || 'Operator (Custom granular permissions)' }}</option>
          <option value="viewer">{{ t('settings_role_viewer') || 'Viewer (Read-only monitoring)' }}</option>
        </select>
      </div>

      <!-- Operator Permissions Checklist (if Operator) -->
      <div v-if="form.role === 'operator'" class="p-3 rounded-lg bg-[#0c1322] border border-cyan-900/40 space-y-2.5">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <span class="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">
            // {{ t('settings_section_perms') || 'Operator Permissions' }}
          </span>
          <div class="flex items-center gap-1">
            <button
              type="button"
              @click="setAllPerms(true)"
              class="px-2 py-0.5 rounded text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-700/60 hover:bg-cyan-900 transition cursor-pointer"
            >
              {{ t('settings_select_all') || 'Select All' }}
            </button>
            <button
              type="button"
              @click="setAllPerms(false)"
              class="px-2 py-0.5 rounded text-[10px] bg-gray-900 text-gray-400 border border-gray-800 hover:text-white transition cursor-pointer"
            >
              {{ t('settings_clear_all') || 'Clear' }}
            </button>
          </div>
        </div>

        <div class="grid grid-cols-1 gap-1.5 max-h-40 overflow-y-auto pr-1">
          <label
            v-for="(meta, permKey) in permissionsMeta"
            :key="permKey"
            class="flex items-start gap-2 p-1.5 rounded bg-[#131c2e] border border-gray-800/80 hover:border-cyan-800/60 transition cursor-pointer text-[11px]"
          >
            <input
              type="checkbox"
              v-model="form.permissions[permKey]"
              class="mt-0.5 rounded text-cyan-500 focus:ring-0"
            />
            <div class="leading-tight">
              <span class="font-bold text-gray-200">{{ t('perm_' + permKey) || meta.label }}</span>
            </div>
          </label>
        </div>
      </div>

      <!-- Server Scope (if Operator) -->
      <div v-if="form.role === 'operator'" class="p-3 rounded-lg bg-[#0c1322] border border-gray-800 space-y-2">
        <div class="text-[10px] font-bold text-gray-300 uppercase tracking-wider">
          // {{ t('settings_section_scope') || 'Server Scope' }}
        </div>
        <div class="space-y-1.5">
          <label class="flex items-center gap-2 cursor-pointer text-[11px]">
            <input
              type="radio"
              name="card_scope_type"
              value="all"
              v-model="scopeType"
              class="text-cyan-500 focus:ring-0"
            />
            <span class="text-gray-200">{{ t('settings_scope_all') || 'All Servers (Global)' }}</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer text-[11px]">
            <input
              type="radio"
              name="card_scope_type"
              value="custom"
              v-model="scopeType"
              class="text-cyan-500 focus:ring-0"
            />
            <span class="text-gray-200">{{ t('settings_scope_specific') || 'Specific Permitted Servers' }}</span>
          </label>
        </div>

        <div v-if="scopeType === 'custom'" class="pt-2 border-t border-gray-800/80 max-h-32 overflow-y-auto space-y-1">
          <label
            v-for="s in serversList"
            :key="s.id"
            class="flex items-center gap-2 p-1 rounded bg-[#131c2e] border border-gray-800 text-[10.5px] cursor-pointer"
          >
            <input
              type="checkbox"
              :value="s.id"
              v-model="form.allowed_server_ids"
              class="rounded text-cyan-500 focus:ring-0"
            />
            <span class="font-bold text-gray-200">{{ s.hostname }}</span>
          </label>
        </div>
      </div>

      <!-- Submit Button -->
      <button
        type="submit"
        :disabled="loading"
        class="w-full py-2 px-3 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-bold transition cursor-pointer flex items-center justify-center gap-2 shadow-sm"
      >
        <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
          <circle cx="8.5" cy="7" r="4"/>
          <line x1="20" y1="8" x2="20" y2="14"/>
          <line x1="23" y1="11" x2="17" y2="11"/>
        </svg>
        <span>{{ loading ? 'Registering...' : (t('settings_add_user_btn_submit') || 'Register User') }}</span>
      </button>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { useI18n } from '../../i18n'

const props = defineProps({
  permissionsMeta: { type: Object, default: () => ({}) },
  serversList: { type: Array, default: () => [] }
})

const emit = defineEmits(['created'])
const { t } = useI18n()

const loading = ref(false)
const errorMsg = ref('')
const scopeType = ref('all')

const form = reactive({
  username: '',
  password: '',
  role: 'operator',
  permissions: {},
  allowed_server_ids: []
})

watch(() => props.permissionsMeta, (meta) => {
  if (meta && Object.keys(meta).length > 0) {
    const p = {}
    Object.keys(meta).forEach(k => { p[k] = false })
    form.permissions = p
  }
}, { immediate: true })

watch(scopeType, (val) => {
  if (val === 'all') {
    form.allowed_server_ids = []
  }
})

function setAllPerms(val) {
  Object.keys(form.permissions).forEach(k => {
    form.permissions[k] = val
  })
}

async function handleSubmit() {
  errorMsg.value = ''
  loading.value = true

  try {
    const token = localStorage.getItem('pantau_token')
    const payload = {
      username: form.username.trim(),
      password: form.password.trim(),
      role: form.role,
      permissions: form.role === 'operator' ? form.permissions : {},
      allowed_server_ids: form.role === 'operator' && scopeType.value === 'custom' ? form.allowed_server_ids : []
    }

    const res = await fetch('/api/users', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    })

    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Failed to create user')
    }

    emit('created', data)

    // Reset Form
    form.username = ''
    form.password = ''
    setAllPerms(false)
    form.allowed_server_ids = []
    scopeType.value = 'all'
  } catch (err) {
    errorMsg.value = err.message
  } finally {
    loading.value = false
  }
}
</script>
