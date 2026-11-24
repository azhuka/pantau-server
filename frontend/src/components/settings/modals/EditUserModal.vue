<template>
  <div class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 overflow-y-auto">
    <div class="bg-[#111827] border border-[#1f2937] rounded-xl w-full max-w-xl p-5 shadow-2xl my-8">
      <div class="flex items-center justify-between pb-3 border-b border-gray-800 mb-4">
        <h3 class="text-sm font-bold text-gray-100 font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>// {{ t('settings_modal_edit_title') }}: <strong class="text-cyan-300">{{ user.username }}</strong></span>
        </h3>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-gray-200 text-sm font-mono cursor-pointer"
        >
          &times;
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <!-- Username Input -->
        <div>
          <label class="block text-xs font-mono font-medium text-gray-300 mb-1">
            {{ t('settings_col_username') }}
          </label>
          <input
            v-model="form.username"
            type="text"
            required
            minlength="3"
            maxlength="50"
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 font-mono focus:outline-none focus:border-cyan-500"
          />
        </div>

        <!-- Optional Password Reset / Update -->
        <div class="p-3 rounded-lg bg-[#0c1322] border border-gray-800 space-y-2">
          <div class="flex items-center justify-between flex-wrap gap-1">
            <span class="text-xs font-mono font-bold text-gray-300">
              {{ t('settings_new_pwd') }} <span class="text-gray-500 font-normal text-[11px]">{{ t('settings_opt_optional') }}</span>
            </span>
            <span class="text-[10px] text-gray-400 font-mono">{{ t('settings_pwd_optional_hint') }}</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <input
                v-model="form.password"
                type="password"
                minlength="8"
                placeholder="New password (optional)"
                class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <input
                v-model="form.confirm_password"
                type="password"
                minlength="8"
                placeholder="Confirm new password"
                class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>
        </div>

        <!-- Role & Status -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-mono font-medium text-gray-300 mb-1">
              {{ t('settings_col_role') }}
            </label>
            <select
              v-model="form.role"
              :disabled="user.role === 'master_admin'"
              class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 font-mono focus:outline-none focus:border-cyan-500 cursor-pointer disabled:opacity-50"
            >
              <option v-if="user.role === 'master_admin'" value="master_admin">{{ t('settings_role_master_admin') }}</option>
              <option value="operator">{{ t('settings_role_operator') }}</option>
              <option value="viewer">{{ t('settings_role_viewer') }}</option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-mono font-medium text-gray-300 mb-1">
              {{ t('settings_col_status') }}
            </label>
            <select
              v-model="form.is_active"
              :disabled="user.role === 'master_admin' || user.id === currentUserId"
              class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 font-mono focus:outline-none focus:border-cyan-500 cursor-pointer disabled:opacity-50"
            >
              <option :value="1">{{ t('settings_status_active') }}</option>
              <option :value="0">{{ t('settings_status_disabled') }}</option>
            </select>
          </div>
        </div>

        <!-- Operator Permissions Checklist (Only for Operator) -->
        <div v-if="form.role === 'operator'" class="p-3 rounded-lg bg-[#0c1322] border border-cyan-900/40 space-y-3">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <span class="text-[11px] font-bold text-cyan-400 font-mono uppercase tracking-wider">
              // {{ t('settings_section_perms') }}
            </span>
            <div class="flex items-center gap-1.5 flex-wrap">
              <button
                type="button"
                @click="applyPreset('full')"
                class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-800 transition cursor-pointer"
              >
                {{ t('settings_preset_full') }}
              </button>
              <button
                type="button"
                @click="applyPreset('sysadmin')"
                class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-800 transition cursor-pointer"
              >
                {{ t('settings_preset_sysadmin') }}
              </button>
              <button
                type="button"
                @click="applyPreset('monitoring')"
                class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-950/80 border border-amber-500/40 text-amber-300 hover:bg-amber-800 transition cursor-pointer"
              >
                {{ t('settings_preset_monitoring') }}
              </button>
              <button
                type="button"
                @click="applyPreset('none')"
                class="px-2 py-0.5 rounded text-[10px] font-mono text-gray-400 bg-gray-800/60 border border-gray-700 hover:text-white transition cursor-pointer"
              >
                {{ t('settings_preset_clear') }}
              </button>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
            <label
              v-for="(meta, permKey) in permissionsMeta"
              :key="permKey"
              class="flex items-start gap-2 p-2 rounded bg-[#131c2e] border border-gray-800 hover:border-cyan-800/60 transition cursor-pointer"
            >
              <input
                type="checkbox"
                v-model="form.permissions[permKey]"
                class="mt-0.5 rounded text-cyan-500 focus:ring-0 cursor-pointer"
              />
              <div class="text-[11px] leading-tight">
                <div class="font-bold text-gray-200 font-mono">{{ t('perm_' + permKey) || meta.label }}</div>
                <div class="text-[10px] text-gray-400 mt-0.5">{{ t('perm_' + permKey + '_desc') || meta.desc }}</div>
              </div>
            </label>
          </div>
        </div>

        <!-- Server Scope (Only for Operator) -->
        <div v-if="form.role === 'operator'" class="p-3 rounded-lg bg-[#0c1322] border border-cyan-900/40 space-y-2.5">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-bold text-cyan-400 font-mono uppercase tracking-wider">
              // {{ t('settings_section_scope') }}
            </span>
          </div>

          <div class="flex items-center gap-4 text-xs font-mono text-gray-300">
            <label class="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                v-model="scopeType"
                value="all"
                class="text-cyan-500 focus:ring-0 cursor-pointer"
              />
              <span>{{ t('settings_scope_all') }}</span>
            </label>
            <label class="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                v-model="scopeType"
                value="custom"
                class="text-cyan-500 focus:ring-0 cursor-pointer"
              />
              <span>{{ t('settings_scope_specific') }}</span>
            </label>
          </div>

          <!-- Custom Server Checkboxes -->
          <div v-if="scopeType === 'custom'" class="pt-2 border-t border-gray-800/80 space-y-2">
            <div class="flex items-center justify-between text-[11px] font-mono text-gray-400">
              <span>{{ t('settings_col_scope') }}:</span>
              <div class="flex gap-2">
                <button
                  type="button"
                  @click="selectAllServers"
                  class="text-cyan-400 hover:underline cursor-pointer"
                >
                  {{ t('settings_select_all') }}
                </button>
                <button
                  type="button"
                  @click="clearAllServers"
                  class="text-gray-400 hover:underline cursor-pointer"
                >
                  {{ t('settings_clear_all') }}
                </button>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-36 overflow-y-auto pr-1">
              <label
                v-for="srv in serversList"
                :key="srv.id"
                class="flex items-center gap-2 p-1.5 rounded bg-[#131c2e] border border-gray-800 text-xs font-mono text-gray-200 cursor-pointer"
              >
                <input
                  type="checkbox"
                  :value="srv.id"
                  v-model="form.allowed_server_ids"
                  class="rounded text-cyan-500 focus:ring-0 cursor-pointer"
                />
                <span class="font-bold">{{ srv.hostname }}</span>
                <span class="text-[10px] text-gray-400">({{ srv.ip_address }})</span>
              </label>
            </div>
          </div>
        </div>

        <div v-if="error" class="p-2.5 rounded bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs font-mono">
          {{ error }}
        </div>

        <div class="flex justify-end gap-2 pt-2 border-t border-gray-800">
          <button
            type="button"
            @click="$emit('close')"
            class="px-3 py-1.5 rounded text-xs font-mono text-gray-400 hover:text-white hover:bg-gray-800 transition cursor-pointer"
          >
            {{ t('settings_btn_cancel') }}
          </button>
          <button
            type="submit"
            :disabled="loading"
            class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-mono font-bold transition cursor-pointer"
          >
            {{ loading ? t('login_verifying') : t('settings_btn_save') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from '../../../i18n'

const props = defineProps({
  user: {
    type: Object,
    required: true
  },
  currentUserId: {
    type: Number,
    default: 0
  },
  permissionsMeta: {
    type: Object,
    default: () => ({})
  },
  serversList: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close', 'updated'])
const { t } = useI18n()

const loading = ref(false)
const error = ref('')
const scopeType = ref(props.user.allowed_server_ids && props.user.allowed_server_ids.length > 0 ? 'custom' : 'all')

const form = reactive({
  username: props.user.username || '',
  password: '',
  confirm_password: '',
  role: props.user.role || 'operator',
  is_active: props.user.is_active ?? 1,
  permissions: {},
  allowed_server_ids: props.user.allowed_server_ids ? [...props.user.allowed_server_ids] : []
})

onMounted(() => {
  const permKeys = Object.keys(props.permissionsMeta)
  const currentPerms = props.user.permissions || {}
  const nextPerms = {}
  permKeys.forEach(k => {
    nextPerms[k] = Boolean(currentPerms[k])
  })
  form.permissions = nextPerms
})

function applyPreset(preset) {
  const permKeys = Object.keys(props.permissionsMeta)
  const nextPerms = {}

  if (preset === 'full') {
    permKeys.forEach(k => { nextPerms[k] = true })
  } else if (preset === 'sysadmin') {
    const sysKeys = ['can_terminal', 'can_file_manager', 'can_services', 'can_processes', 'can_firewall', 'can_cron', 'can_ssl', 'can_apt', 'can_server_control', 'can_probing']
    permKeys.forEach(k => { nextPerms[k] = sysKeys.includes(k) })
  } else if (preset === 'monitoring') {
    const monKeys = ['can_services', 'can_processes', 'can_ssl', 'can_probing', 'can_audit']
    permKeys.forEach(k => { nextPerms[k] = monKeys.includes(k) })
  } else {
    permKeys.forEach(k => { nextPerms[k] = false })
  }

  form.permissions = nextPerms
}

function selectAllServers() {
  form.allowed_server_ids = props.serversList.map(s => s.id)
}

function clearAllServers() {
  form.allowed_server_ids = []
}

async function handleSubmit() {
  if (form.password && form.password !== form.confirm_password) {
    error.value = 'New password and confirmation do not match.'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const token = localStorage.getItem('pantau_token')
    const payload = {
      username: form.username.trim(),
      password: form.password.trim() || null,
      confirm_password: form.confirm_password.trim() || null,
      role: form.role,
      is_active: form.is_active,
      permissions: form.role === 'operator' ? form.permissions : null,
      allowed_server_ids: form.role === 'operator' && scopeType.value === 'custom' ? form.allowed_server_ids : null
    }

    const res = await fetch(`/api/users/${props.user.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Failed to update user')
    }
    emit('updated', data)
    emit('close')
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}
</script>