<template>
  <div
    v-if="tooltipState.visible && tooltipState.text"
    class="fixed pointer-events-auto transition-opacity duration-150 shadow-xl rounded-md bg-[#0a0f1d]/95 border border-gray-700/80 backdrop-blur-sm px-2.5 py-1 text-xs text-gray-200 z-[999999] max-w-sm select-text flex items-center gap-2"
    :style="{ top: `${tooltipState.y}px`, left: `${tooltipState.x}px` }"
    @mouseenter="cancelHide"
    @mouseleave="hideTooltip(false)"
  >
    <div class="leading-snug select-text break-words">
      <span v-if="tooltipState.title" class="font-semibold text-gray-300 mr-1.5">{{ tooltipState.title }}:</span>
      <span :class="tooltipState.code ? 'font-mono text-cyan-300' : 'text-gray-200'">{{ tooltipState.text }}</span>
    </div>
    <button
      v-if="tooltipState.copyable"
      @click.stop="copyContent()"
      class="shrink-0 p-0.5 px-1 rounded hover:bg-gray-800 text-gray-400 hover:text-cyan-300 transition cursor-pointer text-[11px]"
      :title="tooltipState.copied ? 'Copied!' : 'Copy to clipboard'"
    >
      <span v-if="tooltipState.copied" class="text-emerald-400 font-bold">✓</span>
      <span v-else>📋</span>
    </button>
  </div>
</template>

<script setup>
import { tooltipState, cancelHide, hideTooltip, copyContent } from '../../composables/useTooltip'
</script>
