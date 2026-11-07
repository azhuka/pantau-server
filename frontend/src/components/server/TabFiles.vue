<template>
  <div class="space-y-3">
    <!-- Breadcrumb & Toolbar -->
    <div class="flex flex-col sm:flex-row items-center justify-between gap-2 bg-noc-card border border-noc-border p-2.5 rounded-lg text-xs">
      <!-- Path Breadcrumb -->
      <div class="flex items-center gap-1.5 w-full sm:w-auto font-mono overflow-x-auto">
        <span class="text-noc-muted">Direktori:</span>
        <button
          @click="navigate('/')"
          class="px-1.5 py-0.5 rounded hover:bg-white/[0.05] text-noc-cyan font-semibold"
        >
          /
        </button>
        <template v-for="(seg, idx) in pathSegments" :key="idx">
          <span class="text-noc-muted">/</span>
          <button
            @click="navigateToIndex(idx)"
            class="px-1.5 py-0.5 rounded hover:bg-white/[0.05] text-noc-cyan font-medium"
          >
            {{ seg }}
          </button>
        </template>
      </div>

      <!-- Action Buttons -->
      <div class="flex items-center gap-1.5 w-full sm:w-auto justify-end">
        <button @click="refreshDir" class="noc-btn noc-btn-secondary py-1 px-2">
          Segarkan
        </button>
        <button @click="showMkdirModal = true" class="noc-btn noc-btn-secondary py-1 px-2">
          + Folder
        </button>
        <button @click="showTouchModal = true" class="noc-btn noc-btn-secondary py-1 px-2">
          + Berkas
        </button>
      </div>
    </div>

    <!-- Files Table -->
    <div class="noc-card overflow-x-auto">
      <table class="w-full noc-table text-left">
        <thead>
          <tr>
            <th class="w-8"></th>
            <th>Nama Berkas / Folder</th>
            <th class="w-24">Ukuran</th>
            <th class="w-24">Izin (Perms)</th>
            <th class="w-28">Pemilik (Owner)</th>
            <th class="w-36">Waktu Modifikasi</th>
            <th class="w-28 text-right">Aksi</th>
          </tr>
        </thead>
        <tbody>
          <!-- Parent Directory Jump -->
          <tr v-if="currentPath !== '/'" @click="navigateParent" class="cursor-pointer hover:bg-white/[0.04]">
            <td class="text-center font-mono">📁</td>
            <td colspan="6" class="font-mono text-noc-cyan font-semibold">.. (Kembali ke direktori induk)</td>
          </tr>

          <!-- Items -->
          <tr v-for="item in items" :key="item.name" class="group">
            <td class="text-center text-sm">
              <span v-if="item.is_dir">📁</span>
              <span v-else-if="item.is_link">🔗</span>
              <span v-else>📄</span>
            </td>
            <td class="font-mono text-xs font-medium">
              <button
                v-if="item.is_dir"
                @click="navigate(joinPath(currentPath, item.name))"
                class="text-noc-cyan hover:underline text-left"
              >
                {{ item.name }}
              </button>
              <button
                v-else
                @click="viewFile(item)"
                class="text-noc-text hover:text-noc-cyan hover:underline text-left"
              >
                {{ item.name }}
              </button>
            </td>
            <td class="font-mono text-[11px] text-noc-dim">{{ item.is_dir ? '—' : formatBytes(item.size) }}</td>
            <td class="font-mono text-[11px] text-noc-muted">{{ item.mode || '—' }}</td>
            <td class="font-mono text-[11px] text-noc-muted">{{ item.owner || '—' }}:{{ item.group || '—' }}</td>
            <td class="font-mono text-[11px] text-noc-muted">{{ item.mtime || '—' }}</td>
            <td class="text-right space-x-1">
              <button
                v-if="!item.is_dir"
                @click="viewFile(item)"
                class="noc-btn noc-btn-secondary py-0.5 px-1.5 text-[10px]"
                title="Lihat / Edit Berkas"
              >
                Buka
              </button>
              <button
                @click="deleteItem(item)"
                class="noc-btn noc-btn-secondary py-0.5 px-1.5 text-[10px] text-rose-400"
                title="Hapus"
              >
                ✕
              </button>
            </td>
          </tr>

          <tr v-if="items.length === 0 && !loading">
            <td colspan="7" class="text-center py-8 text-noc-muted">Direktori ini kosong</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal: View/Edit File -->
    <div v-if="activeFile" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div class="w-full max-w-4xl h-[85vh] noc-card p-4 border-noc-border shadow-2xl flex flex-col justify-between">
        <div class="flex items-center justify-between pb-3 border-b border-noc-border">
          <div class="font-mono text-xs text-noc-cyan font-bold truncate">
            {{ activeFile.path }}
          </div>
          <div class="flex items-center gap-2">
            <button @click="saveFile" :disabled="saving" class="noc-btn noc-btn-primary py-1 px-3 text-xs">
              {{ saving ? 'Menyimpan...' : 'Simpan Perubahan' }}
            </button>
            <button @click="activeFile = null" class="text-noc-muted hover:text-noc-text text-base">✕</button>
          </div>
        </div>

        <div class="flex-1 my-3 bg-[#090d16] border border-noc-border rounded overflow-hidden">
          <textarea
            v-model="fileContent"
            class="w-full h-full p-3 font-mono text-xs bg-transparent text-noc-text resize-none focus:outline-none"
            spellcheck="false"
          ></textarea>
        </div>

        <div class="flex items-center justify-between text-[11px] text-noc-muted pt-2 border-t border-noc-border">
          <span>Karakter: {{ fileContent.length }}</span>
          <span>Tekan tombol Simpan Perubahan untuk menulis ke node klien</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/api/client'

const props = defineProps({
  serverId: [Number, String],
})

const currentPath = ref('/etc')
const items = ref([])
const loading = ref(false)
const activeFile = ref(null)
const fileContent = ref('')
const saving = ref(false)

const pathSegments = computed(() => {
  return currentPath.value.split('/').filter(Boolean)
})

function joinPath(p1, p2) {
  return `${p1.replace(/\/$/, '')}/${p2}`
}

async function navigate(path) {
  currentPath.value = path
  await refreshDir()
}

function navigateParent() {
  const segs = pathSegments.value
  if (segs.length <= 1) {
    navigate('/')
  } else {
    navigate('/' + segs.slice(0, -1).join('/'))
  }
}

function navigateToIndex(index) {
  const segs = pathSegments.value.slice(0, index + 1)
  navigate('/' + segs.join('/'))
}

async function refreshDir() {
  loading.value = true
  try {
    const res = await api.get(`/api/servers/${props.serverId}/files/ls`, { path: currentPath.value })
    items.value = res?.entries || res?.files || []
  } catch (err) {
    console.error('Gagal membaca direktori:', err)
  } finally {
    loading.value = false
  }
}

async function viewFile(item) {
  const filePath = joinPath(currentPath.value, item.name)
  try {
    const res = await api.get(`/api/servers/${props.serverId}/files/cat`, { path: filePath })
    activeFile.value = { path: filePath, name: item.name }
    fileContent.value = res?.content || ''
  } catch (err) {
    alert('Gagal membaca berkas: ' + err.message)
  }
}

async function saveFile() {
  if (!activeFile.value) return
  saving.value = true
  try {
    await api.post(`/api/servers/${props.serverId}/files/write`, {
      path: activeFile.value.path,
      content: fileContent.value,
    })
    alert('Berkas berhasil disimpan ke server!')
  } catch (err) {
    alert('Gagal menyimpan berkas: ' + err.message)
  } finally {
    saving.value = false
  }
}

async function deleteItem(item) {
  if (!confirm(`Hapus ${item.is_dir ? 'direktori' : 'berkas'} ${item.name}?`)) return
  try {
    await api.post(`/api/servers/${props.serverId}/files/rm`, {
      path: joinPath(currentPath.value, item.name),
    })
    await refreshDir()
  } catch (err) {
    alert('Gagal menghapus: ' + err.message)
  }
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}

onMounted(() => {
  refreshDir()
})
</script>
