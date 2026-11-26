<template>
  <div v-if="isOpen" class="fixed inset-0 z-[100000] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4" @click.self="$emit('close')">
    <div class="hud-tactical-card rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl border border-cyan-500/40 bg-[#0a0f1d] text-gray-200 font-mono">
      <div class="flex items-center justify-between border-b border-gray-800 pb-3">
        <h3 class="text-sm font-bold text-cyan-300 uppercase tracking-wider">
          {{ editingProbe ? 'Edit Synthetic Probe' : 'Add Synthetic Probe' }}
        </h3>
        <button type="button" @click="$emit('close')" class="text-gray-400 hover:text-white cursor-pointer p-1" title="Close">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <form @submit.prevent="save" class="space-y-3 text-xs">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-gray-400 font-bold mb-1">Probe Name</label>
            <input v-model="form.name" required placeholder="e.g. Core API Health" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
          <div>
            <label class="block text-gray-400 font-bold mb-1">Protocol Type</label>
            <select v-model="form.probe_type" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none">
              <option value="https">HTTPS</option>
              <option value="http">HTTP</option>
              <option value="tcp">TCP Port</option>
              <option value="icmp">ICMP Ping</option>
            </select>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-3">
          <div class="col-span-2">
            <label class="block text-gray-400 font-bold mb-1">Target URL / Host</label>
            <input v-model="form.target" required :placeholder="form.probe_type === 'tcp' || form.probe_type === 'icmp' ? '172.30.1.40' : 'https://example.com/health'" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
          <div v-if="form.probe_type === 'tcp'">
            <label class="block text-gray-400 font-bold mb-1">Port</label>
            <input v-model.number="form.port" type="number" min="1" max="65535" required placeholder="443" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
          <div v-else>
            <label class="block text-gray-400 font-bold mb-1">Interval (sec)</label>
            <input v-model.number="form.interval_seconds" type="number" min="10" max="3600" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
        </div>

        <div class="grid grid-cols-3 gap-3">
          <div>
            <label class="block text-gray-400 font-bold mb-1">Timeout (sec)</label>
            <input v-model.number="form.timeout_seconds" type="number" min="1" max="30" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
          <div>
            <label class="block text-gray-400 font-bold mb-1">Latency Warn (ms)</label>
            <input v-model.number="form.latency_threshold_ms" type="number" min="50" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
          <div>
            <label class="block text-gray-400 font-bold mb-1">Linked Asset</label>
            <select v-model="form.server_id" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none">
              <option value="">None (External)</option>
              <option v-for="s in servers" :key="s.id" :value="s.id">{{ s.hostname }}</option>
            </select>
          </div>
        </div>

        <div v-if="form.probe_type === 'http' || form.probe_type === 'https'" class="grid grid-cols-2 gap-3 pt-1 border-t border-gray-800/80">
          <div>
            <label class="block text-gray-400 font-bold mb-1">Expected HTTP Status</label>
            <input v-model="form.expected_status" placeholder="200-299" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
          <div>
            <label class="block text-gray-400 font-bold mb-1">Keyword Match (Optional)</label>
            <input v-model="form.keyword_match" placeholder="ok" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
          </div>
        </div>

        <div class="flex justify-end gap-2 pt-3 border-t border-gray-800">
          <button type="button" @click="$emit('close')" class="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
          <button type="submit" :disabled="saving" class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold cursor-pointer disabled:opacity-50">
            {{ saving ? 'Saving...' : 'Save Probe' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { apiFetch } from '../../utils/api'
import { useToast } from '../../utils/useToast'

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  editingProbe: { type: Object, default: null },
  servers: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'saved'])
const toast = useToast()
const saving = ref(false)

const defaultForm = () => ({
  name: '',
  probe_type: 'https',
  target: '',
  port: null,
  server_id: '',
  interval_seconds: 60,
  timeout_seconds: 5,
  expected_status: '200-299',
  keyword_match: '',
  latency_threshold_ms: 1000,
})
const form = ref(defaultForm())

watch(() => props.isOpen, (open) => {
  if (!open) return
  if (props.editingProbe) {
    form.value = {
      name: props.editingProbe.name || '',
      probe_type: props.editingProbe.probe_type || 'https',
      target: props.editingProbe.target || '',
      port: props.editingProbe.port || null,
      server_id: props.editingProbe.server_id || '',
      interval_seconds: props.editingProbe.interval_seconds || 60,
      timeout_seconds: props.editingProbe.timeout_seconds || 5,
      expected_status: props.editingProbe.expected_status || '200-299',
      keyword_match: props.editingProbe.keyword_match || '',
      latency_threshold_ms: props.editingProbe.latency_threshold_ms || 1000,
    }
  } else {
    form.value = defaultForm()
  }
})

async function save() {
  saving.value = true
  try {
    const url = props.editingProbe ? `/api/probes/${props.editingProbe.id}` : '/api/probes'
    const method = props.editingProbe ? 'PUT' : 'POST'
    const res = await apiFetch(url, { method, body: JSON.stringify(form.value) })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Failed to save probe')
    toast.success(data.message || 'Probe saved')
    emit('saved')
    emit('close')
  } catch (err) {
    toast.error(err.message)
  } finally {
    saving.value = false
  }
}
</script>
