<template>
  <Teleport to="body">
    <div
      v-if="state.isOpen"
      class="fixed inset-0 z-[100015] flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm select-none"
    >
      <div class="w-full max-w-md bg-[#0b1325] border rounded-xl shadow-2xl overflow-hidden font-mono text-xs" :class="borderClass">
        <div class="flex items-center justify-between px-4 py-3 bg-[#0e1930] border-b border-gray-800">
          <span class="font-bold text-gray-100 uppercase tracking-wider text-xs">{{ state.title }}</span>
          <button type="button" @click="cancel" class="text-gray-400 hover:text-white p-1 rounded hover:bg-white/10 cursor-pointer" title="Close">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <form @submit.prevent="accept" class="p-4 space-y-4">
          <p class="text-gray-300 leading-relaxed whitespace-pre-line">{{ state.message }}</p>

          <div v-if="state.requirePassword">
            <label class="block text-gray-400 font-bold mb-1.5">{{ state.passwordLabel }}</label>
            <input
              ref="pwdInput"
              v-model="passwordVal"
              type="password"
              required
              :placeholder="state.passwordPlaceholder"
              class="w-full px-3 py-2 bg-[#060a12] border border-cyan-900/70 rounded text-gray-100 focus:outline-none focus:border-cyan-400"
            />
          </div>

          <div class="flex items-center justify-end gap-2 pt-2 border-t border-gray-800/80">
            <button
              type="button"
              @click="cancel"
              class="px-3.5 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-200 font-bold transition cursor-pointer"
            >
              {{ state.cancelText }}
            </button>
            <button
              type="submit"
              class="px-4 py-1.5 rounded font-bold transition cursor-pointer"
              :class="btnClass"
            >
              {{ state.confirmText }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { useModalEsc } from '../../utils/useModalEsc'
import { ref, computed, watch, nextTick } from 'vue'
import { useConfirmState, resolveConfirm } from '../../utils/useToast'

const state = useConfirmState()
const passwordVal = ref('')
const pwdInput = ref(null)

watch(() => state.value.isOpen, async (open) => {
  passwordVal.value = ''
  if (open && state.value.requirePassword) {
    await nextTick()
    pwdInput.value?.focus()
  }
})

const borderClass = computed(() => {
  if (state.value.variant === 'danger') return 'border-rose-500/60'
  if (state.value.variant === 'warning') return 'border-amber-500/60'
  return 'border-cyan-500/50'
})

const btnClass = computed(() => {
  if (state.value.variant === 'danger') return 'bg-rose-600 hover:bg-rose-500 text-white'
  if (state.value.variant === 'warning') return 'bg-amber-600 hover:bg-amber-500 text-white'
  return 'bg-cyan-600 hover:bg-cyan-500 text-white'
})

function accept() {
  resolveConfirm(state.value.requirePassword ? passwordVal.value : true)
}

function cancel() {
  resolveConfirm(state.value.requirePassword ? null : false)
}
useModalEsc(() => state.isOpen, cancel)
</script>
