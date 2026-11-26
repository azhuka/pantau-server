<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 font-mono text-xs"
    @click.self="$emit('close')"
  >
    <div class="bg-[#0b1220] border border-cyan-500/40 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden">
      <div class="px-5 py-3.5 border-b border-gray-800 flex items-center justify-between bg-[#070c18]">
        <h3 class="text-sm font-bold text-cyan-300 tracking-wide">UI Theme &amp; Density</h3>
        <button
          type="button"
          @click="$emit('close')"
          class="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800/70 cursor-pointer"
          title="Close"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <div class="p-5 space-y-5">
        <div>
          <div class="text-[11px] font-bold uppercase text-gray-400 mb-2">Color Theme</div>
          <div class="grid grid-cols-2 gap-2.5">
            <button
              v-for="th in THEMES"
              :key="th.id"
              type="button"
              @click="selectedTheme = th.id; applyPreferences()"
              :class="[
                'p-3 rounded-lg border text-left transition cursor-pointer',
                selectedTheme === th.id
                  ? 'border-cyan-400 bg-cyan-950/40 text-white'
                  : 'border-gray-800 bg-gray-900/60 text-gray-300 hover:border-gray-700'
              ]"
            >
              <div class="font-bold">{{ th.label }}</div>
              <div class="text-[10px] text-gray-400 mt-0.5">{{ th.desc }}</div>
            </button>
          </div>
        </div>

        <div>
          <div class="text-[11px] font-bold uppercase text-gray-400 mb-2">Accent Color</div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="ac in ACCENTS"
              :key="ac.id"
              type="button"
              @click="selectedAccent = ac.id; applyPreferences()"
              :class="[
                'px-3 py-1.5 rounded border font-bold capitalize transition cursor-pointer',
                selectedAccent === ac.id
                  ? 'border-cyan-400 bg-cyan-950/60 text-white'
                  : 'border-gray-800 bg-gray-900/60 text-gray-400 hover:text-gray-200'
              ]"
            >
              {{ ac.label }}
            </button>
          </div>
        </div>

        <div>
          <div class="text-[11px] font-bold uppercase text-gray-400 mb-2">Table Density</div>
          <div class="grid grid-cols-2 gap-2.5">
            <button
              v-for="den in DENSITIES"
              :key="den.id"
              type="button"
              @click="selectedDensity = den.id; applyPreferences()"
              :class="[
                'p-2.5 rounded-lg border text-left transition cursor-pointer',
                selectedDensity === den.id
                  ? 'border-cyan-400 bg-cyan-950/40 text-white'
                  : 'border-gray-800 bg-gray-900/60 text-gray-300 hover:border-gray-700'
              ]"
            >
              <div class="font-bold">{{ den.label }}</div>
              <div class="text-[10px] text-gray-400">{{ den.desc }}</div>
            </button>
          </div>
        </div>
      </div>

      <div class="px-5 py-3 border-t border-gray-800 bg-[#070c18] flex items-center justify-between">
        <button
          type="button"
          @click="resetDefaults"
          class="px-3 py-1.5 rounded border border-gray-700 text-gray-300 hover:text-white cursor-pointer"
        >
          Reset Defaults
        </button>
        <button
          type="button"
          @click="$emit('close')"
          class="px-4 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 text-white font-bold cursor-pointer"
        >
          Done
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onUnmounted, ref, watch } from 'vue'

const props = defineProps({ isOpen: Boolean })
const emit = defineEmits(['close'])

const THEMES = [
  { id: 'dark', label: 'Midnight NOC', desc: 'Balanced dark slate' },
  { id: 'obsidian', label: 'Obsidian OLED', desc: 'Pure high-contrast black' },
  { id: 'navy', label: 'Deep Space', desc: 'Cool deep blue' },
  { id: 'light', label: 'Light Mode', desc: 'Bright daytime contrast' },
]

const ACCENTS = [
  { id: 'cyan', label: 'Cyan' },
  { id: 'indigo', label: 'Indigo' },
  { id: 'emerald', label: 'Emerald' },
  { id: 'violet', label: 'Violet' },
  { id: 'amber', label: 'Amber' },
]

const DENSITIES = [
  { id: 'compact', label: 'Compact', desc: 'High NOC row density' },
  { id: 'comfortable', label: 'Comfortable', desc: 'Spacious padding' },
]

const selectedTheme = ref(localStorage.getItem('pantau_theme') || 'dark')
const selectedAccent = ref(localStorage.getItem('pantau_accent') || 'cyan')
const selectedDensity = ref(localStorage.getItem('pantau_density') || 'compact')

function applyPreferences() {
  localStorage.setItem('pantau_theme', selectedTheme.value)
  localStorage.setItem('pantau_accent', selectedAccent.value)
  localStorage.setItem('pantau_density', selectedDensity.value)
  document.documentElement.setAttribute('data-theme', selectedTheme.value)
  document.documentElement.setAttribute('data-accent', selectedAccent.value)
  document.documentElement.setAttribute('data-density', selectedDensity.value)
}

function resetDefaults() {
  selectedTheme.value = 'dark'
  selectedAccent.value = 'cyan'
  selectedDensity.value = 'compact'
  applyPreferences()
}

function onEsc(e) {
  if (props.isOpen && e.key === 'Escape') emit('close')
}

watch(() => props.isOpen, (open) => {
  if (open) window.addEventListener('keydown', onEsc)
  else window.removeEventListener('keydown', onEsc)
})

onUnmounted(() => window.removeEventListener('keydown', onEsc))
</script>
