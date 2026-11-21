<template>
  <div
    v-if="tooltipState.visible"
    class="fixed pointer-events-auto transition-opacity duration-150 shadow-[0_10px_35px_-5px_rgba(6,182,212,0.3)] rounded-lg bg-[#0e1626]/95 border border-cyan-500/40 backdrop-blur-md p-3 text-xs text-gray-200 z-[999999] max-w-sm sm:max-w-md select-text"
    :style="{ top: `${tooltipState.y}px`, left: `${tooltipState.x}px` }"
    @mouseenter="cancelHide"
    @mouseleave="hideTooltip(false)"
  >
    <!-- Header with Category/Title & Copy Button -->
    <div class="flex items-center justify-between gap-3 border-b border-gray-700/60 pb-1.5 mb-2 select-none">
      <div class="flex items-center gap-1.5 font-bold tracking-wider uppercase text-[11px] text-cyan-400">
        <span class="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
        <span>{{ tooltipState.title || (locale === 'id' ? 'INFORMASI' : 'INFORMATION') }}</span>
      </div>
      <button
        v-if="tooltipState.copyable && tooltipState.text"
        @click.stop="copyContent()"
        class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono transition font-medium cursor-pointer"
        :class="tooltipState.copied ? 'bg-emerald-950 text-emerald-400 border border-emerald-600/70' : 'bg-gray-800/90 hover:bg-cyan-950/80 text-gray-300 hover:text-cyan-200 border border-gray-700/80'"
        :title="locale === 'id' ? 'Klik untuk menyalin teks ini ke papan klip' : 'Click to copy this text to clipboard'"
      >
        <span>{{ tooltipState.copied ? '✓' : '📋' }}</span>
        <span>{{ tooltipState.copied ? (locale === 'id' ? 'Tersalin!' : 'Copied!') : (locale === 'id' ? 'Salin' : 'Copy') }}</span>
      </button>
    </div>

    <!-- Content Area: Selectable Text & Optional Monospace Code Box -->
    <div class="select-text">
      <div
        v-if="tooltipState.code"
        class="font-mono text-xs text-cyan-200 bg-[#060910] p-2.5 rounded border border-gray-800/80 break-all max-h-52 overflow-y-auto leading-relaxed select-text"
      >
        {{ tooltipState.text }}
      </div>
      <div
        v-else
        class="text-gray-100 text-xs leading-relaxed break-words select-text"
      >
        {{ tooltipState.text }}
      </div>
    </div>

    <!-- Optional Extra Info / Context -->
    <div
      v-if="tooltipState.extra"
      class="mt-2 pt-1.5 border-t border-gray-800/80 text-[11px] text-gray-400 font-mono select-text flex items-center justify-between"
    >
      <span>{{ tooltipState.extra }}</span>
      <span class="text-cyan-500/70 text-[10px]">{{ locale === 'id' ? 'Teks dapat disorot & disalin' : 'Selectable text' }}</span>
    </div>
  </div>
</template>

<script setup>
import { tooltipState, cancelHide, hideTooltip, copyContent } from '../../composables/useTooltip'
import { useI18n } from '../../i18n'

const { locale } = useI18n()
</script>
