<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[20000] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm select-none"
  >
    <div class="relative w-full max-w-lg bg-[#0b1325] border border-cyan-500/50 rounded-xl shadow-[0_20px_60px_rgba(0,0,0,0.9)] overflow-hidden font-mono text-xs">
      <!-- Modal Header -->
      <div class="flex items-center justify-between px-5 py-3.5 bg-[#0e1930] border-b border-cyan-900/60">
        <div class="flex items-center gap-2.5">
          <svg class="w-4 h-4 text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" x2="8" y1="13" y2="13"/>
            <line x1="16" x2="8" y1="17" y2="17"/>
            <line x1="10" x2="8" y1="9" y2="9"/>
          </svg>
          <span class="font-bold text-gray-200 uppercase tracking-wider text-sm">{{ t('modal_edit_note_title') }}</span>
          <span v-if="server" class="px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/60 text-[10px]">
            {{ server.hostname }}
          </span>
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

      <!-- Form Body -->
      <form @submit.prevent="saveNote" class="p-5 space-y-4 text-left">
        <div>
          <textarea
            v-model="notesContent"
            rows="8"
            class="w-full p-3 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400 transition resize-y font-mono text-xs leading-relaxed"
            :placeholder="t('host_note_placeholder')"
          ></textarea>
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
            type="submit"
            :disabled="submitting"
            class="px-5 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold transition cursor-pointer disabled:opacity-50 flex items-center gap-2"
          >
            <svg v-if="submitting" class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
            </svg>
            <span>{{ t('btn_save') || 'Save' }}</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { useModalEsc } from '../../../utils/useModalEsc'
import { ref, watch } from 'vue'
import { useI18n } from '../../../i18n'
import { useToast } from '../../../utils/useToast'

const props = defineProps({
  isOpen: Boolean,
  server: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'updated'])
const { t } = useI18n()
const toast = useToast()

const submitting = ref(false)
const notesContent = ref('')

watch([() => props.isOpen, () => props.server], ([open, s]) => {
  if (open && s) {
    notesContent.value = s.notes || ''
  }
}, { immediate: true })

async function saveNote() {
  if (!props.server) return
  submitting.value = true
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}/note`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: JSON.stringify({ notes: notesContent.value })
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      emit('updated', data.message || 'Note updated')
      emit('close')
    } else {
      toast.error(data.detail || data.error || 'Failed to update note')
    }
  } catch (err) {
    toast.error('Error: ' + err.message)
  } finally {
    submitting.value = false
  }
}
useModalEsc(() => props.isOpen, () => emit('close'))
</script>
