<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="hud-card p-4 rounded-xl flex items-center justify-between">
      <div>
        <h2 class="text-base font-bold text-gray-100 uppercase tracking-wide flex items-center gap-2">
          <span>⚙️</span>
          <span>{{ t('settings_title') }}</span>
        </h2>
        <p class="text-xs text-gray-400 mt-0.5">
          {{ t('settings_subtitle') }}
        </p>
      </div>
    </div>

    <!-- RBAC & User Management Overview -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="hud-card p-4 rounded-xl space-y-3">
        <h3 class="text-sm font-bold text-gray-200 uppercase tracking-wider border-b border-gray-800 pb-2">
          🛡️ {{ t('rbac_title') }}
        </h3>
        <div class="text-sm text-gray-300 space-y-2.5 leading-relaxed">
          <p>
            ● <strong class="text-blue-400">{{ t('rbac_master_admin').split(':')[0] }}:</strong> {{ t('rbac_master_admin').split(':')[1] }}
          </p>
          <p>
            ● <strong class="text-emerald-400">{{ t('rbac_full_operator').split(':')[0] }}:</strong> {{ t('rbac_full_operator').split(':')[1] }}
          </p>
          <p>
            ● <strong class="text-gray-400">{{ t('rbac_protect_accounts').split(':')[0] }}:</strong> {{ t('rbac_protect_accounts').split(':')[1] }}
          </p>
        </div>
      </div>

      <div class="hud-card p-4 rounded-xl space-y-3">
        <h3 class="text-sm font-bold text-gray-200 uppercase tracking-wider border-b border-gray-800 pb-2">
          📡 {{ t('threshold_title') }}
        </h3>
        <div class="text-sm text-gray-300 space-y-2 leading-relaxed">
          <div class="flex justify-between items-center py-1.5 border-b border-gray-800/60">
            <span>{{ t('threshold_cpu') }}</span>
            <span class="font-bold text-rose-400 font-mono">85%</span>
          </div>
          <div class="flex justify-between items-center py-1.5 border-b border-gray-800/60">
            <span>{{ t('threshold_ram') }}</span>
            <span class="font-bold text-rose-400 font-mono">90%</span>
          </div>
          <div class="flex justify-between items-center py-1.5 border-b border-gray-800/60">
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
