<template>
  <div class="noc-card p-4 space-y-3">
    <div class="flex items-center justify-between pb-2 border-b border-noc-border">
      <div>
        <h3 class="text-xs font-bold uppercase tracking-wider text-noc-text flex items-center gap-2">
          <span>📝</span>
          <span>Catatan Operasional & Dokumentasi Server</span>
        </h3>
        <p class="text-[11px] text-noc-muted mt-0.5">Catat prosedur pemulihan, topologi IP, atau riwayat insiden penting server ini</p>
      </div>

      <button
        @click="saveNotes"
        :disabled="saving"
        class="noc-btn noc-btn-primary py-1 px-3"
      >
        {{ saving ? 'Menyimpan...' : 'Simpan Catatan' }}
      </button>
    </div>

    <div>
      <textarea
        v-model="notes"
        rows="12"
        placeholder="Tuliskan catatan operasional di sini..."
        class="w-full p-3 font-mono text-xs bg-noc-bg border border-noc-border rounded text-noc-text focus:outline-none focus:border-noc-cyan resize-y"
      ></textarea>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { api } from '@/api/client'

const props = defineProps({
  serverId: [Number, String],
  initialNotes: String,
})

const notes = ref(props.initialNotes || '')
const saving = ref(false)

watch(() => props.initialNotes, (newVal) => {
  if (newVal !== undefined) notes.value = newVal
})

async function saveNotes() {
  saving.value = true
  try {
    await api.post(`/api/servers/${props.serverId}/notes`, { notes: notes.value })
    alert('Catatan berhasil diperbarui!')
  } catch (err) {
    alert('Gagal menyimpan catatan: ' + err.message)
  } finally {
    saving.value = false
  }
}
</script>
