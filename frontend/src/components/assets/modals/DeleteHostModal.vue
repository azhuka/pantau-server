<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none"
  >
    <div class="relative w-full max-w-md bg-[#0b1325] border border-rose-500/50 rounded-xl shadow-[0_20px_60px_rgba(0,0,0,0.9)] overflow-hidden font-mono text-xs">
      <!-- Modal Header -->
      <div class="flex items-center justify-between px-5 py-3.5 bg-rose-950/40 border-b border-rose-900/60">
        <div class="flex items-center gap-2.5">
          <svg class="w-4 h-4 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h18"/>
            <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
            <line x1="10" x2="10" y1="11" y2="17"/>
            <line x1="14" x2="14" y1="11" y2="17"/>
          </svg>
          <span class="font-bold text-rose-300 uppercase tracking-wider text-sm">{{ t('modal_delete_host_title') }}</span>
        </div>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-white p-1 rounded hover:bg-white/10 transition cursor-pointer"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Warning Body -->
      <div class="p-5 space-y-4 text-left">
        <div v-if="server" class="p-3.5 rounded bg-rose-950/30 border border-rose-800/40 text-rose-200 leading-relaxed">
          <div class="font-bold text-white mb-1.5 flex items-center gap-2">
            <svg class="w-4 h-4 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <span>{{ t('modal_delete_host_confirm') }} <strong class="text-rose-400">{{ server.hostname }}</strong> ({{ server.ip_address }})?</span>
          </div>
          <div class="text-[11px] text-gray-300">{{ t('modal_delete_host_warning') }}</div>
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center justify-end gap-2.5 pt-3 border-t border-cyan-900/60">
          <button
            type="button"
            @click="$emit('close')"
            class="px-4 py-2 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold transition cursor-pointer"
          >
            {{ t('btn_cancel') || 'Cancel' }}
          </button>
          <button
            type="button"
            :disabled="submitting"
            @click="confirmDelete"
            class="px-5 py-2 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold transition cursor-pointer disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="submitting" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            </svg>
            <span>{{ t('act_delete_host') }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useModalEsc } from '../../../utils/useModalEsc'
import { ref } from 'vue'
import { useI18n } from '../../../i18n'
import { useToast } from '../../../utils/useToast'

const toast = useToast()

const props = defineProps({
  isOpen: Boolean,
  server: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'deleted'])
const { t } = useI18n()
const submitting = ref(false)

async function confirmDelete() {
  if (!props.server) return
  submitting.value = true
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}`, {
      method: 'DELETE',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      }
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      emit('deleted', data.message || 'Host deleted')
      emit('close')
    } else {
      toast.error(data.detail || data.error || 'Failed to delete host')
    }
  } catch (err) {
    toast.error('Error: ' + err.message)
  } finally {
    submitting.value = false
  }
}
useModalEsc(() => props.isOpen, () => emit('close'))
</script>
