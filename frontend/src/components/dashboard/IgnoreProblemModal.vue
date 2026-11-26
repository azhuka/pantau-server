<template>
  <div
    v-if="isOpen && problem"
    class="fixed inset-0 z-70 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 font-mono select-none"
  >
    <div class="hud-tactical-card rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl border border-amber-500/50">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- Header -->
      <div class="flex items-center justify-between border-b border-gray-800 pb-3">
        <div class="flex items-center gap-2 text-amber-400 font-bold text-xs uppercase">
          <svg class="w-4 h-4 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/><line x1="2" y1="2" x2="22" y2="22"/>
          </svg>
          <span>{{ t('ipm_title') }}</span>
        </div>
        <button @click="$emit('close')" class="text-gray-400 hover:text-white cursor-pointer" :title="t('btn_close')">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Problem Target -->
      <div class="space-y-1.5 text-xs">
        <div class="text-gray-400">{{ t('ipm_target_incident') }}</div>
        <div class="bg-[#060a14] p-2.5 rounded border border-gray-800 text-gray-200">
          <div class="font-bold text-cyan-300">{{ problem.hostname || `Server #${problem.server_id}` }}</div>
          <div class="text-xs text-gray-300 mt-0.5 line-clamp-2">{{ formatIncidentMessage(problem, locale) }}</div>
        </div>
      </div>

      <!-- Duration Selection -->
      <div class="space-y-1.5 text-xs">
        <label class="text-gray-300 font-bold block">{{ t('ipm_duration_label') }}</label>
        <select
          v-model="duration"
          class="w-full bg-[#060a14] border border-gray-700 text-gray-200 rounded p-2 text-xs focus:border-amber-400 focus:outline-none cursor-pointer"
        >
          <option value="incident">{{ t('ipm_dur_incident') }}</option>
          <option value="2h">{{ t('ipm_dur_2h') }}</option>
          <option value="24h">{{ t('ipm_dur_24h') }}</option>
          <option value="7d">{{ t('ipm_dur_7d') }}</option>
          <option value="30d">{{ t('ipm_dur_30d') }}</option>
          <option value="permanent">{{ t('ipm_dur_permanent') }}</option>
        </select>
      </div>

      <!-- Reason Input -->
      <div class="space-y-1.5 text-xs">
        <label class="text-gray-300 font-bold block">{{ t('ipm_reason_label') }}</label>
        <textarea
          v-model="reason"
          rows="2"
          :placeholder="t('ipm_reason_placeholder')"
          class="w-full bg-[#060a14] border border-gray-700 text-gray-200 rounded p-2 text-xs focus:border-amber-400 focus:outline-none"
        ></textarea>
      </div>

      <!-- Footer Buttons -->
      <div class="flex items-center justify-end gap-2 pt-2 border-t border-gray-800 text-xs">
        <button
          @click="$emit('close')"
          class="px-3 py-1.5 rounded bg-gray-800 text-gray-300 hover:text-white font-bold transition cursor-pointer"
          :title="t('ipm_btn_cancel_tooltip')"
        >
          {{ t('ipm_btn_cancel') }}
        </button>
        <button
          :disabled="submitting"
          @click="submitIgnore"
          class="px-4 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white font-bold transition cursor-pointer disabled:opacity-50"
          :title="t('ipm_btn_submit_tooltip')"
        >
          {{ submitting ? t('ipm_btn_saving') : t('ipm_btn_submit') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useI18n } from '../../i18n'
import { formatIncidentMessage } from '../../utils/formatters'
import { useToast } from '../../utils/useToast'

const { t, locale } = useI18n()
const toast = useToast()

const props = defineProps({
  isOpen: Boolean,
  problem: { type: Object, default: null },
  currentUser: { type: Object, default: null }
})

const emit = defineEmits(['close', 'ignored'])

const duration = ref('incident')
const reason = ref('')
const submitting = ref(false)

watch(() => props.isOpen, (open) => {
  if (open) {
    duration.value = 'incident'
    reason.value = ''
  }
})

async function submitIgnore() {
  if (!props.problem) return
  const r = (props.currentUser?.role || '').toLowerCase()
  if (['viewer', 'guest', 'tamu'].includes(r)) {
    toast.error('Access denied: Viewer accounts cannot ignore incidents.')
    emit('close')
    return
  }
  submitting.value = true
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch(`/api/problems/${props.problem.id}/ignore`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        duration: duration.value,
        reason: reason.value.trim()
      })
    })
    const data = await res.json()
    if (data.ok) {
      emit('ignored', {
        id: props.problem.id,
        duration: duration.value,
        reason: reason.value.trim()
      })
      emit('close')
    } else {
      toast.error(data.detail || 'Failed to ignore incident')
    }
  } catch (err) {
    console.error('Failed to ignore incident:', err)
  } finally {
    submitting.value = false
  }
}
</script>
