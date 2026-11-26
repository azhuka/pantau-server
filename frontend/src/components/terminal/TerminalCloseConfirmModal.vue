<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[36000] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none"
  >
    <div class="relative w-full max-w-md bg-[#0b1325] border border-cyan-500/50 rounded-xl shadow-[0_20px_60px_rgba(0,0,0,0.9)] overflow-hidden font-mono text-xs">
      <div class="flex items-center justify-between px-5 py-3.5 bg-[#0e1930] border-b border-cyan-900/60">
        <div class="flex items-center gap-2.5">
          <svg class="w-4 h-4 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span class="font-bold text-gray-200 uppercase tracking-wider text-sm">{{ t('modal_terminal_close_title') }}</span>
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
          {{ t('terminal_close_desc_1') }}
        </p>
        <p class="text-gray-400 text-[11px] leading-relaxed">
          {{ t('terminal_close_desc_2') }}
        </p>

        <div class="flex items-center justify-end gap-2.5 pt-4 border-t border-cyan-900/60">
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
            class="px-4 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition cursor-pointer"
          >
            {{ t('btn_close_terminal_view') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../../i18n'

defineProps({
  isOpen: Boolean
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
