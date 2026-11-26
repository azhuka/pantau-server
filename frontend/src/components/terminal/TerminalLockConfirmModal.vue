<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[36000] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none"
  >
    <div class="relative w-full max-w-md bg-[#0b1325] border border-rose-500/50 rounded-xl shadow-[0_20px_60px_rgba(0,0,0,0.9)] overflow-hidden font-mono text-xs">
      <div class="flex items-center justify-between px-5 py-3.5 bg-rose-950/40 border-b border-rose-900/60">
        <div class="flex items-center gap-2.5 text-rose-400">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          <span class="font-bold uppercase tracking-wider text-sm">{{ t('modal_terminal_lock_title') }}</span>
        </div>
        <button
          @click="handleClose"
          class="text-gray-400 hover:text-white p-1 rounded hover:bg-white/10 transition cursor-pointer"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div class="p-5 space-y-3 text-left">
        <p class="text-gray-200 text-xs leading-relaxed">
          {{ t('terminal_lock_desc_1') }}
        </p>
        <p class="text-gray-400 text-[11px] leading-relaxed">
          {{ t('terminal_lock_desc_2') }}
        </p>

        <div class="flex items-center justify-end gap-2.5 pt-4 border-t border-rose-900/50">
          <button
            type="button"
            @click="handleClose"
            class="px-4 py-2 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold transition cursor-pointer"
          >
            {{ t('btn_cancel') || 'Cancel' }}
          </button>
          <button
            type="button"
            @click="handleConfirm"
            class="px-4 py-2 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold transition cursor-pointer flex items-center gap-2"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <span>{{ t('btn_lock_terminal_confirm') }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../../i18n'

defineProps({
  isOpen: Boolean,
  server: Object
})

const emit = defineEmits(['close', 'confirm'])
const { t } = useI18n()

function handleClose() {
  emit('close')
}

function handleConfirm() {
  emit('confirm')
}
</script>
