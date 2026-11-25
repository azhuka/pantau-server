<template>
  <Teleport to="body">
    <div v-if="toasts.length > 0" class="fixed bottom-12 right-5 z-[100020] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="pointer-events-auto flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border shadow-2xl font-mono text-xs backdrop-blur-md transition-all"
        :class="toastClass(item.type)"
      >
        <svg v-if="item.type === 'success'" class="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
        <svg v-else-if="item.type === 'error'" class="w-4 h-4 shrink-0 mt-0.5 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
        <svg v-else-if="item.type === 'warning'" class="w-4 h-4 shrink-0 mt-0.5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        <svg v-else class="w-4 h-4 shrink-0 mt-0.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        <span class="flex-1 leading-snug break-words">{{ item.message }}</span>
        <button type="button" @click="dismiss(item.id)" class="text-gray-400 hover:text-white cursor-pointer shrink-0" title="Dismiss">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { useToast } from '../../utils/useToast'

const { toasts, dismiss } = useToast()

function toastClass(type) {
  if (type === 'success') return 'bg-[#071a15]/95 border-emerald-500/50 text-emerald-100'
  if (type === 'error') return 'bg-[#1c0910]/95 border-rose-500/60 text-rose-100'
  if (type === 'warning') return 'bg-[#1c1507]/95 border-amber-500/60 text-amber-100'
  return 'bg-[#091529]/95 border-cyan-500/50 text-cyan-100'
}
</script>
