<template>
  <div class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 overflow-y-auto font-mono text-xs" @click.self="$emit('close')">
    <div class="bg-[#111827] border border-amber-600/50 rounded-xl w-full max-w-lg p-5 shadow-2xl my-8 space-y-4">
      <!-- Header -->
      <div class="flex items-center justify-between pb-3 border-b border-gray-800">
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-full bg-amber-400"></div>
          <h3 class="text-sm font-bold text-gray-100 uppercase tracking-wider">
            {{ t('settings_recovery_codes_title') || 'Backup Recovery Codes (2FA)' }}
          </h3>
        </div>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-gray-200 text-sm cursor-pointer"
        >
          &times;
        </button>
      </div>

      <!-- Warning & Notice -->
      <div class="p-3 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-200 text-[11px] leading-relaxed">
        <p class="font-bold mb-1">
          {{ t('settings_recovery_notice_bold') || 'Important Security Notice:' }}
        </p>
        <p>
          {{ t('settings_recovery_notice_desc') || 'These backup recovery codes are displayed only once. Each code can only be used once if you lose access to your authenticator app.' }}
        </p>
      </div>

      <!-- Codes Grid -->
      <div class="grid grid-cols-2 gap-2 p-3 rounded-lg bg-[#0c1322] border border-gray-800">
        <div
          v-for="(code, idx) in codes"
          :key="idx"
          class="p-2 rounded bg-black/60 border border-gray-800 text-center font-mono font-bold text-cyan-300 text-sm tracking-wider select-all"
        >
          {{ code }}
        </div>
      </div>

      <!-- Copy & Download Buttons -->
      <div class="flex items-center gap-2 pt-2">
        <button
          type="button"
          @click="copyAllCodes"
          class="flex-1 py-2 rounded bg-gray-800 hover:bg-gray-700 text-gray-200 font-bold transition cursor-pointer text-center text-xs flex items-center justify-center gap-1.5"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="13" height="13" x="9" y="9" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span>{{ copied ? (t('settings_copied') || 'Copied to Clipboard') : (t('settings_copy_all_codes') || 'Copy All Codes') }}</span>
        </button>

        <button
          type="button"
          @click="downloadCodes"
          class="flex-1 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold transition cursor-pointer text-center text-xs flex items-center justify-center gap-1.5"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          <span>{{ t('settings_download_txt') || 'Download (.txt)' }}</span>
        </button>
      </div>

      <!-- Footer -->
      <div class="flex justify-end pt-3 border-t border-gray-800">
        <button
          type="button"
          @click="$emit('close')"
          class="px-5 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition cursor-pointer text-xs"
        >
          {{ t('settings_done') || 'Done' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from '../../../i18n'

const props = defineProps({
  codes: { type: Array, default: () => [] }
})

defineEmits(['close'])
const { t } = useI18n()

const copied = ref(false)

function copyAllCodes() {
  const text = (props.codes || []).join('\n')
  navigator.clipboard.writeText(text).then(() => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 3000)
  })
}

function downloadCodes() {
  const text = [
    '=== PANTAU SERVER 2FA RECOVERY CODES ===',
    `Generated at: ${new Date().toISOString()}`,
    'Each code can only be used once for emergency login.',
    '',
    ...(props.codes || [])
  ].join('\n')

  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `pantau-2fa-recovery-codes-${Date.now()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}
</script>
