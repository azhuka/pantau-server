<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="hud-tactical-card p-3.5 px-4 rounded-xl flex items-center justify-between shadow-lg">
      <span class="hud-corner-tr"></span>
      <span class="hud-corner-bl"></span>

      <div>
        <h2 class="text-sm font-bold text-gray-100 uppercase tracking-wider font-mono flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-cyan-400 beacon-live"></span>
          <span>// SETTINGS: RBAC & OPERATIONAL PARAMETERS</span>
        </h2>
        <p class="text-xs text-gray-400 font-mono mt-0.5">
          {{ t('settings_subtitle') }}
        </p>
      </div>
    </div>

    <!-- RBAC & User Management Overview -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
      <div class="hud-tactical-card p-4 rounded-xl space-y-3 shadow-lg">
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>

        <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider border-b border-cyan-500/20 pb-2">
          // {{ t('rbac_title') }}
        </h3>
        <div class="text-xs text-gray-300 space-y-2.5 leading-relaxed">
          <p>
            ● <strong class="text-cyan-400">{{ t('rbac_master_admin').split(':')[0] }}:</strong> {{ t('rbac_master_admin').split(':')[1] }}
          </p>
          <p>
            ● <strong class="text-emerald-400">{{ t('rbac_full_operator').split(':')[0] }}:</strong> {{ t('rbac_full_operator').split(':')[1] }}
          </p>
          <p>
            ● <strong class="text-gray-400">{{ t('rbac_protect_accounts').split(':')[0] }}:</strong> {{ t('rbac_protect_accounts').split(':')[1] }}
          </p>
        </div>
      </div>

      <div class="hud-tactical-card p-4 rounded-xl space-y-3 shadow-lg">
        <span class="hud-corner-tr"></span>
        <span class="hud-corner-bl"></span>

        <h3 class="text-xs font-bold text-gray-100 uppercase tracking-wider border-b border-cyan-500/20 pb-2">
          // {{ t('threshold_title') }}
        </h3>
        <div class="text-xs text-gray-300 space-y-2 leading-relaxed">
          <div class="flex justify-between items-center py-1.5 border-b border-cyan-500/10">
            <span>{{ t('threshold_cpu') }}</span>
            <span class="font-bold text-rose-400 font-mono">85%</span>
          </div>
          <div class="flex justify-between items-center py-1.5 border-b border-cyan-500/10">
            <span>{{ t('threshold_ram') }}</span>
            <span class="font-bold text-rose-400 font-mono">90%</span>
          </div>
          <div class="flex justify-between items-center py-1.5 border-b border-cyan-500/10">
            <span>{{ t('threshold_ssh') }}</span>
            <span class="font-bold text-emerald-400 font-mono">{{ t('threshold_active') }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from '../../i18n'

const { t } = useI18n()
</script>
