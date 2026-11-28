<template>
  <div v-if="isOpen" class="fixed inset-0 z-[100000] bg-black/75 backdrop-blur-sm flex items-center justify-center p-4" @keydown.esc="closeModal">
    <div class="hud-tactical-card rounded-xl max-w-2xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-cyan-500/40 bg-[#0a0f1d] text-gray-200 font-mono overflow-hidden">
      <div class="flex items-center justify-between border-b border-gray-800 px-5 py-3.5 shrink-0">
        <h3 class="text-sm font-bold text-cyan-300 uppercase tracking-wider">
          {{ isEdit ? 'Edit Endpoint Probe' : 'Add Endpoint Probe' }}
        </h3>
        <button type="button" @click="closeModal" class="text-gray-400 hover:text-white cursor-pointer p-1" title="Close">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <form @submit.prevent="submit" class="flex flex-col flex-1 min-h-0">
        <div class="p-5 space-y-4 text-xs overflow-y-auto flex-1">
          <!-- Protocol Selector -->
          <div>
            <label class="block text-gray-400 font-bold mb-1.5 uppercase">Probe Type</label>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="opt in typeOptions"
                :key="opt.key"
                type="button"
                @click="selectType(opt.key)"
                class="px-3 py-2 rounded border text-left transition cursor-pointer flex items-center gap-2"
                :class="activeCategory === opt.key ? 'bg-cyan-950/70 border-cyan-500 text-cyan-200 font-bold' : 'bg-[#070c18] border-gray-800 text-gray-400 hover:border-gray-700 hover:text-gray-200'"
              >
                <span class="w-2 h-2 rounded-full shrink-0" :class="activeCategory === opt.key ? 'bg-cyan-400' : 'bg-gray-600'"></span>
                <span>{{ opt.label }}</span>
              </button>
            </div>
          </div>

          <!-- Name & Environment -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-gray-400 font-bold mb-1">Endpoint Name *</label>
              <input v-model="form.name" required maxlength="100" placeholder="e.g. Main Portal API, Core Router" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
            </div>
            <div>
              <label class="block text-gray-400 font-bold mb-1">Environment &amp; Criticality</label>
              <select v-model="form.tier" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none">
                <option :value="1">Production — Crucial (Core)</option>
                <option :value="3">Production — Standard (Supporting)</option>
                <option :value="2">Non-Production (Staging / Test)</option>
              </select>
            </div>
          </div>

          <!-- Target & Linked Asset -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-gray-400 font-bold mb-1">
                {{ activeCategory === 'web' ? 'Target URL *' : 'Target Host / IP *' }}
              </label>
              <input
                v-model="form.target"
                required
                :placeholder="activeCategory === 'web' ? 'https://example.com or http://172.30.1.10:8080' : 'e.g. 172.30.1.1 or db.internal'"
                class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
            <div>
              <label class="block text-gray-400 font-bold mb-1">
                Linked Asset {{ isScopedOperator ? '*' : '(Optional)' }}
              </label>
              <select v-model="form.server_id" :required="isScopedOperator" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none">
                <option v-if="!isScopedOperator" value="">-- Standalone / External --</option>
                <option v-for="s in servers" :key="s.id" :value="s.id">{{ s.hostname }} ({{ s.ip_address }})</option>
              </select>
            </div>
          </div>

          <!-- TCP Port -->
          <div v-if="activeCategory === 'tcp'" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-gray-400 font-bold mb-1">TCP Port *</label>
              <input v-model.number="form.port" type="number" min="1" max="65535" required placeholder="e.g. 3306, 5432, 443" class="w-full bg-[#070c18] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100 focus:border-cyan-500 focus:outline-none" />
            </div>
          </div>

          <!-- Advanced Settings -->
          <details class="border border-gray-800 rounded-lg p-3 bg-[#070c18]/60">
            <summary class="cursor-pointer text-cyan-300 font-bold select-none">Advanced Settings (Optional)</summary>
            <div class="mt-3 space-y-3">
              <div v-if="activeCategory === 'web'" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label class="block text-gray-400 font-bold mb-1">HTTP Method</label>
                  <select v-model="form.http_method" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100">
                    <option value="GET">GET</option>
                    <option value="HEAD">HEAD</option>
                    <option value="POST">POST</option>
                  </select>
                </div>
                <div>
                  <label class="block text-gray-400 font-bold mb-1">Expected Status</label>
                  <input v-model="form.expected_status" placeholder="200-299" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
                </div>
                <div>
                  <label class="block text-gray-400 font-bold mb-1">Keyword Match (Optional)</label>
                  <input v-model="form.keyword_match" placeholder="Required text in response body" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
                </div>
                <div class="flex items-end pb-1.5">
                  <label class="flex items-center gap-2 text-gray-300 cursor-pointer">
                    <input type="checkbox" v-model="form.ssl_verify" class="accent-cyan-500" />
                    <span>Verify TLS / SSL Certificate</span>
                  </label>
                </div>
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div>
                  <label class="block text-gray-400 font-bold mb-1">Interval (sec)</label>
                  <input v-model.number="form.interval_seconds" type="number" min="10" max="3600" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
                </div>
                <div>
                  <label class="block text-gray-400 font-bold mb-1">Timeout (sec)</label>
                  <input v-model.number="form.timeout_seconds" type="number" min="1" max="30" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
                </div>
                <div>
                  <label class="block text-gray-400 font-bold mb-1">Latency Warn (ms)</label>
                  <input v-model.number="form.latency_threshold_ms" type="number" min="50" max="30000" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
                </div>
                <div>
                  <label class="block text-gray-400 font-bold mb-1">Fail Threshold</label>
                  <input v-model.number="form.consecutive_threshold" type="number" min="1" max="10" class="w-full bg-[#0a0f1d] border border-gray-700 rounded px-2.5 py-1.5 text-gray-100" />
                </div>
              </div>
            </div>
          </details>

          <!-- Ad-hoc Test Result -->
          <div
            v-if="testResult"
            class="p-2.5 rounded border text-xs flex items-center justify-between gap-2"
            :class="testResult.status === 'up' ? 'bg-emerald-950/40 border-emerald-700/60 text-emerald-300' : (testResult.status === 'degraded' ? 'bg-amber-950/40 border-amber-700/60 text-amber-300' : 'bg-rose-950/40 border-rose-700/60 text-rose-300')"
          >
            <div>
              <span class="font-bold uppercase">{{ testResult.status }}</span>
              <span v-if="testResult.latency_ms !== null && testResult.latency_ms !== undefined" class="ml-2">({{ Math.round(testResult.latency_ms) }} ms)</span>
              <span v-if="testResult.status_code" class="ml-2 text-gray-300">HTTP {{ testResult.status_code }}</span>
              <span v-if="testResult.error_message" class="ml-2 text-rose-200">— {{ testResult.error_message }}</span>
            </div>
          </div>
        </div>

        <div class="flex items-center justify-between gap-2 px-5 py-3.5 border-t border-gray-800 bg-[#070c18]/80 shrink-0 text-xs">
          <button
            type="button"
            @click="runAdhocTest"
            :disabled="testing || !form.target.trim()"
            class="px-3 py-1.5 rounded bg-gray-800 hover:bg-cyan-950 text-cyan-300 border border-cyan-700/50 font-bold cursor-pointer disabled:opacity-40"
          >
            {{ testing ? 'Testing...' : 'Test Connection' }}
          </button>
          <div class="flex items-center gap-2">
            <button type="button" @click="closeModal" class="px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer">Cancel</button>
            <button type="submit" :disabled="saving" class="px-4 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold cursor-pointer disabled:opacity-50">
              {{ saving ? 'Saving...' : (isEdit ? 'Save Changes' : 'Add Endpoint') }}
            </button>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { useModalEsc } from '../../../utils/useModalEsc'
import { ref, computed, watch } from 'vue'
import { apiFetch, extractErrorMessage } from '../../../utils/api'
import { useToast } from '../../../utils/useToast'

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  probe: { type: Object, default: null },
  servers: { type: Array, default: () => [] },
  isScopedOperator: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])
const toast = useToast()

const typeOptions = [
  { key: 'web', label: 'Web (HTTP/HTTPS)' },
  { key: 'icmp', label: 'Network Ping (ICMP)' },
  { key: 'tcp', label: 'TCP Port' },
]

const defaultForm = () => ({
  name: '',
  probe_type: 'https',
  target: '',
  port: null,
  server_id: '',
  tier: 1,
  interval_seconds: 60,
  timeout_seconds: 5,
  http_method: 'GET',
  expected_status: '200-299',
  keyword_match: '',
  ssl_verify: true,
  latency_threshold_ms: 1000,
  consecutive_threshold: 3,
})

const form = ref(defaultForm())
const activeCategory = ref('web')
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)
const isEdit = computed(() => Boolean(props.probe && props.probe.id))

watch(() => [props.isOpen, props.probe], ([open]) => {
  if (!open) return
  testResult.value = null
  if (props.probe) {
    const pt = (props.probe.probe_type || 'http').toLowerCase()
    activeCategory.value = (pt === 'http' || pt === 'https') ? 'web' : pt
    form.value = {
      name: props.probe.name || '',
      probe_type: pt,
      target: props.probe.target || '',
      port: props.probe.port ?? null,
      server_id: props.probe.server_id ?? '',
      tier: props.probe.tier ?? 1,
      interval_seconds: props.probe.interval_seconds || 60,
      timeout_seconds: props.probe.timeout_seconds || 5,
      http_method: props.probe.http_method || 'GET',
      expected_status: props.probe.expected_status || '200-299',
      keyword_match: props.probe.keyword_match || '',
      ssl_verify: props.probe.ssl_verify !== false,
      latency_threshold_ms: props.probe.latency_threshold_ms || 1000,
      consecutive_threshold: props.probe.consecutive_threshold || 3,
    }
  } else {
    activeCategory.value = 'web'
    form.value = defaultForm()
    if (props.isScopedOperator && props.servers?.length) {
      form.value.server_id = props.servers[0].id
    }
  }
})

function selectType(cat) {
  activeCategory.value = cat
  testResult.value = null
  if (cat === 'web') form.value.probe_type = form.value.target.startsWith('http://') ? 'http' : 'https'
  else form.value.probe_type = cat
}

function buildPayload() {
  const payload = { ...form.value }
  if (activeCategory.value === 'web') {
    payload.probe_type = payload.target.trim().toLowerCase().startsWith('http://') ? 'http' : 'https'
    payload.port = null
  } else {
    payload.probe_type = activeCategory.value
  }
  payload.server_id = payload.server_id === '' ? null : Number(payload.server_id)
  return payload
}

async function runAdhocTest() {
  testing.value = true
  testResult.value = null
  try {
    const res = await apiFetch('/api/probes/test-adhoc', { method: 'POST', body: JSON.stringify(buildPayload()) })
    const data = await res.json()
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Probe test failed'))
    testResult.value = data.result
  } catch (err) {
    toast.error(err.message)
  } finally {
    testing.value = false
  }
}

async function submit() {
  saving.value = true
  try {
    const url = isEdit.value ? `/api/probes/${props.probe.id}` : '/api/probes'
    const method = isEdit.value ? 'PUT' : 'POST'
    const res = await apiFetch(url, { method, body: JSON.stringify(buildPayload()) })
    const data = await res.json()
    if (!res.ok) throw new Error(extractErrorMessage(data, 'Failed to save endpoint'))
    toast.success(data.message || 'Endpoint saved')
    emit('saved')
    closeModal()
  } catch (err) {
    toast.error(err.message)
  } finally {
    saving.value = false
  }
}

function closeModal() {
  testResult.value = null
  emit('close')
}
useModalEsc(() => props.isOpen, closeModal)
</script>
