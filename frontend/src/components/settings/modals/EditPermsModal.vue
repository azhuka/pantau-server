<template>
  <div class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 overflow-y-auto font-mono">
    <div class="bg-[#111827] border border-[#1f2937] rounded-xl w-full max-w-xl p-5 shadow-2xl my-8 text-xs">
      <!-- Header -->
      <div class="flex items-center justify-between pb-3 border-b border-gray-800 mb-4">
        <div>
          <h3 class="text-sm font-bold text-gray-100 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
            <span>// {{ t('settings_modal_perms_title') || 'Configure Operator Permissions' }}: <strong class="text-cyan-300">{{ user.username }}</strong></span>
          </h3>
          <p class="text-[11px] text-gray-400 mt-0.5">
            {{ t('settings_modal_perms_desc') || 'Manage granular capabilities and asset scoping.' }}
          </p>
        </div>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-gray-200 text-sm cursor-pointer"
        >
          &times;
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <!-- Role Selection -->
        <div>
          <label class="block text-xs font-medium text-gray-300 mb-1">
            {{ t('settings_col_role') || 'Role' }}
          </label>
          <select
            v-model="form.role"
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500 cursor-pointer"
          >
            <option value="operator">{{ t('settings_role_operator') || 'Operator (Custom granular permissions)' }}</option>
            <option value="viewer">{{ t('settings_role_viewer') || 'Viewer (Read-only monitoring)' }}</option>
          </select>
        </div>

        <!-- Operator Permissions Checklist (Only for Operator) -->
        <div v-if="form.role === 'operator'" class="p-3 rounded-lg bg-[#0c1322] border border-cyan-900/40 space-y-3">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <span class="text-[11px] font-bold text-cyan-400 uppercase tracking-wider">
              // {{ t('settings_section_perms') || 'Operator Permissions Matrix' }}
            </span>
            <div class="flex items-center gap-1.5 flex-wrap">
              <button
                type="button"
                @click="applyPreset('full')"
                class="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-800 transition cursor-pointer"
              >
                {{ t('settings_preset_full') || 'Full Sudo' }}
              </button>
              <button
                type="button"
                @click="applyPreset('sysadmin')"
                class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-800 transition cursor-pointer"
              >
                {{ t('settings_preset_sysadmin') || 'Maintenance' }}
              </button>
              <button
                type="button"
                @click="applyPreset('monitoring')"
                class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 border border-amber-500/40 text-amber-300 hover:bg-amber-800 transition cursor-pointer"
              >
                {{ t('settings_preset_monitoring') || 'Monitoring L1' }}
              </button>
              <button
                type="button"
                @click="applyPreset('none')"
                class="px-2 py-0.5 rounded text-[10px] text-gray-400 bg-gray-800/60 border border-gray-700 hover:text-white transition cursor-pointer"
              >
                {{ t('settings_preset_clear') || 'Clear All' }}
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
                <div class="font-bold text-gray-200">{{ t('perm_' + permKey) || meta.label }}</div>
                <div class="text-[10px] text-gray-400 mt-0.5">{{ t('perm_' + permKey + '_desc') || meta.desc }}</div>
              </div>
            </label>
          </div>
        </div>

        <!-- Monitored Assets Scope (Only for Operator) -->
        <div v-if="form.role === 'operator'" class="p-3 rounded-lg bg-[#0c1322] border border-gray-800 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-bold text-cyan-400 uppercase tracking-wider">
              // {{ t('settings_section_scope') || 'Monitored Assets Scope' }}
            </span>
          </div>

          <div class="space-y-2">
            <label class="flex items-center gap-2 cursor-pointer text-xs">
              <input
                type="radio"
                name="scope_type"
                value="all"
                v-model="scopeType"
                class="text-cyan-500 focus:ring-0"
              />
              <span class="font-bold text-gray-200">{{ t('settings_scope_all') || 'All Servers (Global Operator)' }}</span>
            </label>

            <label class="flex items-center gap-2 cursor-pointer text-xs">
              <input
                type="radio"
                name="scope_type"
                value="custom"
                v-model="scopeType"
                class="text-cyan-500 focus:ring-0"
              />
              <span class="font-bold text-gray-200">{{ t('settings_scope_specific') || 'Specific Permitted Servers' }}</span>
            </label>
          </div>

          <!-- Specific Servers List -->
          <div v-if="scopeType === 'custom'" class="pt-2 border-t border-gray-800 space-y-2">
            <div class="flex items-center justify-between text-[11px] text-gray-400">
              <span>Select accessible servers:</span>
              <div class="flex gap-2">
                <button
                  type="button"
                  @click="selectAllServers(true)"
                  class="text-cyan-400 hover:underline cursor-pointer"
                >
                  {{ t('settings_select_all') || 'Select All' }}
                </button>
                <button
                  type="button"
                  @click="selectAllServers(false)"
                  class="text-gray-400 hover:underline cursor-pointer"
                >
                  {{ t('settings_clear_all') || 'Clear' }}
                </button>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-36 overflow-y-auto pr-1">
              <label
                v-for="s in serversList"
                :key="s.id"
                class="flex items-center gap-2 p-1.5 rounded bg-[#131c2e] border border-gray-800 text-[11px] cursor-pointer hover:border-cyan-800/60"
              >
                <input
                  type="checkbox"
                  :value="s.id"
                  v-model="form.allowed_server_ids"
                  class="rounded text-cyan-500 focus:ring-0"
                />
                <span class="font-bold text-gray-200">{{ s.hostname }}</span>
                <span class="text-[10px] text-gray-500">({{ s.ip }})</span>
              </label>
            </div>
          </div>
        </div>

        <!-- Error Message -->
        <div v-if="errorMsg" class="p-2 rounded bg-rose-950/80 border border-rose-800 text-rose-300 text-[11px]">
          {{ errorMsg }}
        </div>

        <!-- Actions -->
        <div class="flex items-center justify-end gap-2 pt-3 border-t border-gray-800">
          <button
            type="button"
            @click="$emit('close')"
            class="px-3 py-1.5 rounded text-gray-400 hover:text-white transition cursor-pointer"
          >
            {{ t('settings_btn_cancel') || 'Cancel' }}
          </button>
          <button
            type="submit"
            :disabled="loading"
            class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition cursor-pointer disabled:opacity-50"
          >
            {{ loading ? 'Saving...' : (t('settings_btn_save') || 'Save Permissions') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { useI18n } from '../../../i18n'

const props = defineProps({
  user: { type: Object, required: true },
  permissionsMeta: { type: Object, default: () => ({}) },
  serversList: { type: Array, default: () => [] }
})

const emit = defineEmits(['close', 'updated'])
const { t } = useI18n()

const loading = ref(false)
const errorMsg = ref('')

const scopeType = ref(
  props.user.allowed_server_ids && props.user.allowed_server_ids.length > 0 ? 'custom' : 'all'
)

const form = reactive({
  role: props.user.role || 'operator',
  permissions: { ...(props.user.permissions || {}) },
  allowed_server_ids: [...(props.user.allowed_server_ids || [])]
})

watch(scopeType, (newVal) => {
  if (newVal === 'all') {
    form.allowed_server_ids = []
  }
})

function applyPreset(preset) {
  const allKeys = Object.keys(props.permissionsMeta || {})
  if (preset === 'none') {
    allKeys.forEach(k => { form.permissions[k] = false })
  } else if (preset === 'full') {
    allKeys.forEach(k => { form.permissions[k] = true })
  } else if (preset === 'sysadmin') {
    allKeys.forEach(k => {
      form.permissions[k] = ['can_services', 'can_packages', 'can_terminal', 'can_cron', 'can_firewall'].includes(k)
    })
  } else if (preset === 'monitoring') {
    allKeys.forEach(k => {
      form.permissions[k] = ['can_audit', 'can_logs', 'can_export'].includes(k)
    })
  }
}

function selectAllServers(select) {
  if (select) {
    form.allowed_server_ids = props.serversList.map(s => s.id)
  } else {
    form.allowed_server_ids = []
  }
}

async function handleSubmit() {
  errorMsg.value = ''
  loading.value = true

  try {
    const token = localStorage.getItem('pantau_token')
    const payload = {
      role: form.role,
      permissions: form.role === 'operator' ? form.permissions : {},
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
      throw new Error(data.detail || 'Failed to update permissions')
    }

    emit('updated', data)
    emit('close')
  } catch (err) {
    errorMsg.value = err.message
  } finally {
    loading.value = false
  }
}
</script>
