<template>
  <div class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 overflow-y-auto">
    <div class="bg-[#111827] border border-[#1f2937] rounded-xl w-full max-w-md p-5 shadow-2xl my-8 font-mono text-xs">
      <!-- Header -->
      <div class="flex items-center justify-between pb-3 border-b border-gray-800 mb-4">
        <div>
          <h3 class="text-sm font-bold text-gray-100 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
            <span>{{ t('settings_modal_edit_self_title') || 'Edit Account Credentials' }}</span>
          </h3>
          <p class="text-[11px] text-gray-400 mt-0.5">
            {{ user.username }} &bull; {{ user.is_master_admin ? 'Master Admin' : user.role }}
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
        <!-- Username -->
        <div>
          <label class="block text-xs font-medium text-gray-300 mb-1">
            {{ t('settings_col_username') || 'Username' }}
          </label>
          <input
            v-model="form.username"
            type="text"
            required
            minlength="3"
            maxlength="50"
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500"
          />
        </div>

        <!-- Current Password (Required to authorize self changes) -->
        <div>
          <label class="block text-xs font-medium text-gray-300 mb-1">
            {{ t('settings_current_pwd') || 'Current Password' }} <span class="text-rose-400">*</span>
          </label>
          <input
            v-model="form.current_password"
            type="password"
            required
            placeholder="Enter current password to authorize changes"
            class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500"
          />
          <p class="text-[10px] text-gray-400 mt-1">
            {{ t('settings_current_pwd_hint') || 'Required to verify your identity before saving changes.' }}
          </p>
        </div>

        <!-- New Password & Confirm Password (Optional) -->
        <div class="p-3 rounded-lg bg-[#0c1322] border border-gray-800 space-y-2">
          <div class="flex items-center justify-between flex-wrap gap-1">
            <span class="text-xs font-bold text-gray-300">
              {{ t('settings_new_pwd') || 'New Password' }} <span class="text-gray-500 font-normal text-[11px]">{{ t('settings_opt_optional') || '(Optional)' }}</span>
            </span>
            <span class="text-[10px] text-gray-400">
              {{ t('settings_pwd_optional_hint') || 'Leave blank to keep unchanged.' }}
            </span>
          </div>

          <div class="space-y-2">
            <input
              v-model="form.password"
              type="password"
              minlength="8"
              placeholder="New password (optional)"
              class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500"
            />
            <input
              v-model="form.confirm_password"
              type="password"
              minlength="8"
              placeholder="Confirm new password"
              class="w-full bg-[#161f30] border border-[#1f2937] text-gray-100 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>

        <!-- Session Security Notice -->
        <div class="p-2.5 rounded bg-amber-950/30 border border-amber-900/50 text-amber-200 text-[10.5px] leading-relaxed">
          <strong>Security Notice:</strong> Changing your password will automatically invalidate all your other active sessions across devices.
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
            {{ loading ? 'Saving...' : (t('settings_btn_save') || 'Save Changes') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { useModalEsc } from '../../../utils/useModalEsc'
import { ref, reactive } from 'vue'
import { useI18n } from '../../../i18n'

const props = defineProps({
  user: { type: Object, required: true }
})

const emit = defineEmits(['close', 'updated'])
const { t } = useI18n()

const loading = ref(false)
const errorMsg = ref('')

const form = reactive({
  username: props.user.username || '',
  current_password: '',
  password: '',
  confirm_password: ''
})

async function handleSubmit() {
  errorMsg.value = ''

  if (form.password && form.password !== form.confirm_password) {
    errorMsg.value = t('settings_pwd_mismatch') || 'New password and confirmation do not match.'
    return
  }

  loading.value = true
  try {
    const token = localStorage.getItem('pantau_token')
    const payload = {
      username: form.username.trim(),
      current_password: form.current_password.trim(),
    }
    if (form.password) {
      payload.password = form.password.trim()
      payload.confirm_password = form.confirm_password.trim()
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
      throw new Error(data.detail || 'Failed to update credentials')
    }

    emit('updated', data)
    emit('close')
  } catch (err) {
    errorMsg.value = err.message
  } finally {
    loading.value = false
  }
}
useModalEsc(() => true, () => emit('close'))
</script>
