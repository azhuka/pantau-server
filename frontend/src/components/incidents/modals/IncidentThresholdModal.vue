<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-70 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 font-mono select-none"
    @click.self="$emit('close')"
  >
    <div class="hud-tactical-card rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl border border-cyan-500/40 bg-[#0a0f1d] text-gray-200">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <!-- Header -->
      <div class="flex items-center justify-between border-b border-gray-800 pb-3">
        <div class="flex items-center gap-2 text-cyan-400 font-bold text-xs uppercase tracking-wider">
          <svg class="w-4 h-4 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span>{{ t('inc_threshold_modal_title') }}</span>
        </div>
        <button @click="$emit('close')" class="text-gray-400 hover:text-white cursor-pointer" :title="t('btn_close')">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <p class="text-xs text-gray-400 leading-relaxed">{{ t('inc_threshold_desc') }}</p>

      <!-- Form Grid -->
      <div class="grid grid-cols-2 gap-3 text-xs">
        <div class="bg-[#060a14] p-3 rounded border border-gray-800 space-y-2">
          <div class="text-cyan-300 font-bold flex items-center justify-between">
            <span>CPU Thresholds</span>
            <span class="text-[10px] text-gray-500">%</span>
          </div>
          <div class="space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-amber-400 text-[11px]">Warning:</span>
              <input v-model.number="form.cpu_warning" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-orange-400 text-[11px]">Critical:</span>
              <input v-model.number="form.cpu_critical" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-red-400 text-[11px]">Danger:</span>
              <input v-model.number="form.cpu_danger" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
          </div>
        </div>

        <div class="bg-[#060a14] p-3 rounded border border-gray-800 space-y-2">
          <div class="text-cyan-300 font-bold flex items-center justify-between">
            <span>RAM Thresholds</span>
            <span class="text-[10px] text-gray-500">%</span>
          </div>
          <div class="space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-amber-400 text-[11px]">Warning:</span>
              <input v-model.number="form.ram_warning" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-orange-400 text-[11px]">Critical:</span>
              <input v-model.number="form.ram_critical" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-red-400 text-[11px]">Danger:</span>
              <input v-model.number="form.ram_danger" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
          </div>
        </div>

        <div class="bg-[#060a14] p-3 rounded border border-gray-800 space-y-2">
          <div class="text-cyan-300 font-bold flex items-center justify-between">
            <span>Disk Thresholds</span>
            <span class="text-[10px] text-gray-500">%</span>
          </div>
          <div class="space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-amber-400 text-[11px]">Warning:</span>
              <input v-model.number="form.disk_warning" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-orange-400 text-[11px]">Critical:</span>
              <input v-model.number="form.disk_critical" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-red-400 text-[11px]">Danger:</span>
              <input v-model.number="form.disk_danger" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
          </div>
        </div>

        <div class="bg-[#060a14] p-3 rounded border border-gray-800 space-y-2">
          <div class="text-cyan-300 font-bold flex items-center justify-between">
            <span>Swap & SSH</span>
            <span class="text-[10px] text-gray-500">Rules</span>
          </div>
          <div class="space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-amber-400 text-[11px]">Swap Warn:</span>
              <input v-model.number="form.swap_warning" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-red-400 text-[11px]">Swap Danger:</span>
              <input v-model.number="form.swap_danger" type="number" min="1" max="100" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
            <div class="flex items-center justify-between">
              <span class="text-amber-400 text-[11px]">SSH Warn (>sess):</span>
              <input v-model.number="form.ssh_warning" type="number" min="0" max="20" class="w-16 bg-gray-900 border border-gray-700 rounded px-1.5 py-0.5 text-right text-xs" />
            </div>
          </div>
        </div>
      </div>

      <!-- Footer Buttons -->
      <div class="flex items-center justify-end gap-2 pt-3 border-t border-gray-800 text-xs">
        <button
          @click="$emit('close')"
          class="px-3 py-1.5 rounded bg-gray-800 text-gray-300 hover:text-white font-bold transition cursor-pointer"
        >
          {{ t('btn_cancel') || 'Cancel' }}
        </button>
        <button
          v-if="canEdit"
          :disabled="saving"
          @click="saveThresholds"
          class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition cursor-pointer disabled:opacity-50"
        >
          {{ saving ? (t('saving') || 'Saving...') : t('inc_threshold_save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../../../i18n'

const { t } = useI18n()

const props = defineProps({
  isOpen: Boolean,
  thresholds: { type: Object, default: () => ({}) },
  currentUser: { type: Object, default: null }
})

const emit = defineEmits(['close', 'saved'])

const form = ref({
  cpu_warning: 80,
  cpu_critical: 90,
  cpu_danger: 95,
  ram_warning: 80,
  ram_critical: 90,
  ram_danger: 95,
  disk_warning: 85,
  disk_critical: 90,
  disk_danger: 95,
  swap_warning: 70,
  swap_danger: 85,
  ssh_warning: 1
})

const saving = ref(false)

const canEdit = computed(() => {
  const r = (props.currentUser?.role || '').toLowerCase()
  return !['viewer', 'guest', 'tamu'].includes(r)
})

watch(() => props.thresholds, (val) => {
  if (val && Object.keys(val).length > 0) {
    form.value = { ...form.value, ...val }
  }
}, { immediate: true })

async function saveThresholds() {
  if (!canEdit.value) return
  saving.value = true
  try {
    const token = localStorage.getItem('pantau_token')
    const res = await fetch('/api/problems/thresholds', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify(form.value)
    })
    const data = await res.json()
    if (data.ok) {
      emit('saved', data.thresholds)
      emit('close')
    } else {
      alert(data.detail || 'Failed to save thresholds')
    }
  } catch (err) {
    console.error('Failed to save thresholds:', err)
  } finally {
    saving.value = false
  }
}
</script>