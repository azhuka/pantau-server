<template>
  <div class="hud-tactical-card rounded-xl p-4 font-mono space-y-3">
    <span class="hud-corner-tr"></span>
    <span class="hud-corner-bl"></span>
    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
        <h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider">
          // APT PACKAGES &amp; UPDATES
        </h3>
      </div>
      <span class="text-xs text-amber-300 font-bold">{{ server?.apt_upgradable || 0 }} upgradable packages</span>
    </div>
    <div class="text-xs text-gray-300 leading-relaxed">
      {{ t('ws_packages_desc') }}
    </div>
    <div v-if="(packagesList || []).length > 0" class="overflow-x-auto max-h-[400px]">
      <table class="w-full text-left text-xs border-collapse">
        <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold">
          <tr>
            <th class="py-2 px-3">{{ t('col_pkg_name') }}</th>
            <th class="py-2 px-3">{{ t('col_pkg_current') }}</th>
            <th class="py-2 px-3">{{ t('col_pkg_new') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-800/40">
          <tr v-for="(pkg, idx) in packagesList" :key="idx" class="hover:bg-cyan-950/20">
            <td class="py-2 px-3 font-semibold text-gray-200">{{ pkg.name }}</td>
            <td class="py-2 px-3 text-gray-400">{{ pkg.current_version || '-' }}</td>
            <td class="py-2 px-3 text-emerald-400 font-bold">{{ pkg.candidate_version || pkg.new_version || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../../../i18n'

const { t } = useI18n()

defineProps({
  server: { type: Object, default: () => ({}) },
  packagesList: { type: Array, default: () => [] }
})
</script>
