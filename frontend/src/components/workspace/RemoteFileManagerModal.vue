<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[10000] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 transition-all"
    :class="{ '!p-0': isFullscreen || isFullWindow }"
    @click.self="emit('close')"
    @keydown.esc="handleEsc"
  >
    <div
      class="bg-[#070b16] border border-cyan-500/50 shadow-[0_25px_60px_rgba(0,0,0,0.95)] flex flex-col transition-all overflow-hidden font-mono relative"
      :class="[
        isFullscreen || isFullWindow
          ? 'w-full h-full rounded-none border-none'
          : 'w-[95vw] max-w-[1260px] h-[84vh] min-h-[560px] rounded-xl'
      ]"
    >
      <!-- FM Header -->
      <div class="bg-[#090f20] border-b border-cyan-500/30 px-4 py-2 flex items-center justify-between select-none">
        <div class="flex items-center gap-2.5 min-w-0">
          <svg class="w-4 h-4 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
          </svg>
          <span class="text-xs font-bold text-cyan-300 uppercase tracking-wider shrink-0">
            // REMOTE FILE MANAGER · {{ server?.hostname || 'Host' }}
          </span>
          <span
            v-if="server?.ip_address"
            class="text-[11px] px-1.5 py-0.5 rounded bg-cyan-950/80 border border-cyan-800 text-cyan-200 cursor-pointer hover:border-cyan-400 hidden sm:inline"
            @click="copyIp(server.ip_address)"
            title="Click to copy IP"
          >
            {{ server.ip_address }}
          </span>
        </div>

        <!-- Window Controls -->
        <div class="flex items-center gap-1 text-xs">
          <!-- Full Window -->
          <button
            @click="isFullWindow = !isFullWindow"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-cyan-300 hover:bg-gray-800/80 transition cursor-pointer"
            :title="isFullWindow ? 'Restore window' : 'Full Window'"
          >
            <svg v-if="!isFullWindow" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="18" height="18" x="3" y="3" rx="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
            </svg>
            <svg v-else class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="13" height="13" x="8" y="3" rx="1.5"/>
              <path d="M4 8H3a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-1"/>
            </svg>
          </button>
          <!-- Fullscreen -->
          <button
            @click="isFullscreen = !isFullscreen"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-cyan-300 hover:bg-gray-800/80 transition cursor-pointer"
            :title="isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="15 3 21 3 21 9"/>
              <polyline points="9 21 3 21 3 15"/>
              <line x1="21" y1="3" x2="14" y2="10"/>
              <line x1="3" y1="21" x2="10" y2="14"/>
            </svg>
          </button>
          <!-- Popout -->
          <button
            @click="popoutWindow"
            class="w-7 h-7 flex items-center justify-center rounded text-cyan-400 hover:text-white bg-cyan-950/60 hover:bg-cyan-900 border border-cyan-800/50 hover:border-cyan-500 transition cursor-pointer"
            title="Pop-out Window"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/>
              <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </button>
          <!-- Close -->
          <button
            @click="emit('close')"
            class="w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-rose-400 hover:bg-rose-950/60 transition cursor-pointer"
            title="Close (Esc)"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Navigation & Address Bar (Dual Mode) -->
      <div class="bg-[#050812] border-b border-cyan-500/20 px-3 py-1.5 flex items-center gap-2 flex-wrap">
        <!-- Navigation Buttons -->
        <div class="flex items-center gap-1 shrink-0">
          <button
            type="button"
            class="w-7 h-7 rounded border border-gray-700 bg-gray-900/80 hover:bg-gray-800 text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center cursor-pointer transition"
            :disabled="historyIndex <= 0"
            @click="goBack"
            title="Back"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
          <button
            type="button"
            class="w-7 h-7 rounded border border-gray-700 bg-gray-900/80 hover:bg-gray-800 text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center cursor-pointer transition"
            :disabled="historyIndex >= historyStack.length - 1"
            @click="goForward"
            title="Forward"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>
          <button
            type="button"
            class="w-7 h-7 rounded border border-gray-700 bg-gray-900/80 hover:bg-gray-800 text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center cursor-pointer transition"
            :disabled="currentPath === '/' || !currentPath"
            @click="navigateUp"
            title="Up One Level"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="18 15 12 9 6 15"/>
            </svg>
          </button>
          <button
            type="button"
            class="w-7 h-7 rounded border border-gray-700 bg-gray-900/80 hover:bg-gray-800 text-gray-300 flex items-center justify-center cursor-pointer transition"
            @click="loadDirectory('/root')"
            title="Home (~)"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
              <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
          </button>
          <button
            type="button"
            class="w-7 h-7 rounded border border-gray-700 bg-gray-900/80 hover:bg-gray-800 text-gray-300 flex items-center justify-center cursor-pointer transition"
            @click="refreshCurrent"
            title="Refresh Directory"
          >
            <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
              <path d="M3 3v5h5"/>
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
              <path d="M16 21h5v-5"/>
            </svg>
          </button>
        </div>

        <!-- Address Bar Container -->
        <div class="flex-1 min-w-[260px] bg-[#020409] border border-cyan-900/80 focus-within:border-cyan-400 rounded px-2.5 py-1 flex items-center gap-1.5 transition text-xs">
          <!-- Mode 1: Interactive Breadcrumbs -->
          <div v-if="!isManualPathInput" class="flex items-center gap-1 overflow-x-auto whitespace-nowrap scrollbar-none flex-1 select-none">
            <span
              @click="loadDirectory('/')"
              class="px-1.5 py-0.5 rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/60 cursor-pointer font-bold"
              :class="{ '!text-cyan-300 font-extrabold': currentPath === '/' }"
            >
              /
            </span>
            <template v-for="(seg, idx) in breadcrumbSegments" :key="idx">
              <span class="text-cyan-800 text-[11px]">&gt;</span>
              <span
                @click="loadDirectory(seg.path)"
                class="px-1.5 py-0.5 rounded cursor-pointer transition"
                :class="idx === breadcrumbSegments.length - 1 ? 'text-gray-100 font-bold bg-cyan-950/40' : 'text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/40'"
              >
                {{ seg.name }}
              </span>
            </template>
          </div>

          <!-- Mode 2: Manual Path Input Form -->
          <form v-else class="flex items-center gap-1.5 flex-1" @submit.prevent="submitManualPath">
            <span class="text-cyan-400 font-bold">&gt;</span>
            <input
              ref="manualPathInputRef"
              v-model="manualPathInputValue"
              type="text"
              class="flex-1 bg-transparent border-none text-gray-100 text-xs font-mono focus:outline-none"
              placeholder="/enter/path/here"
              @keydown.esc="isManualPathInput = false"
            />
            <button
              type="button"
              class="text-gray-400 hover:text-gray-200 text-sm px-1 cursor-pointer"
              @click="isManualPathInput = false"
              title="Cancel"
            >
              ✕
            </button>
          </form>

          <!-- Toggle Manual Input Button -->
          <button
            type="button"
            class="text-gray-400 hover:text-cyan-300 p-1 rounded hover:bg-gray-800 transition cursor-pointer shrink-0"
            @click="toggleManualPathInput"
            title="Edit / Paste Path Manually"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
            </svg>
          </button>

          <!-- Open Terminal at Path -->
          <button
            type="button"
            class="text-gray-400 hover:text-cyan-300 p-1 rounded hover:bg-gray-800 transition cursor-pointer shrink-0"
            @click="emitTerminalAtPath"
            :title="t('fm_terminal_at_path') || 'Open Web Terminal at this path'"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="4 17 10 11 4 5"/>
              <line x1="12" y1="19" x2="20" y2="19"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Dynamic Bookmarks Bar (Physically verified on host) -->
      <div v-if="bookmarks.length > 0" class="bg-[#04060d] border-b border-cyan-500/15 px-3 py-1 flex items-center gap-1.5 flex-wrap text-[11px] select-none">
        <span class="text-[10px] uppercase font-bold text-gray-400 flex items-center gap-1 tracking-wider mr-1">
          <svg class="w-3 h-3 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
          </svg>
          {{ t('fm_bookmarks_label') || 'Bookmarks:' }}
        </span>
        <button
          v-for="bm in bookmarks"
          :key="bm.path"
          type="button"
          class="px-2 py-0.5 rounded border transition cursor-pointer"
          :class="currentPath === bm.path ? 'bg-cyan-950 text-cyan-300 border-cyan-600 font-bold' : 'bg-gray-900/60 text-gray-400 border-gray-800 hover:text-cyan-200 hover:border-cyan-800'"
          @click="loadDirectory(bm.path)"
          :title="bm.title"
        >
          {{ bm.label }}
        </button>
      </div>

      <!-- Action & Filter Bar -->
      <div class="bg-[#050811] border-b border-cyan-500/20 px-3 py-1.5 flex items-center justify-between gap-3 text-xs flex-wrap">
        <div class="flex items-center gap-1.5">
          <!-- + New File -->
          <button
            type="button"
            @click="showNewFileDialog = true"
            class="px-2.5 py-1 rounded bg-gray-900 hover:bg-cyan-950 text-cyan-300 border border-cyan-800 hover:border-cyan-500 transition flex items-center gap-1 cursor-pointer font-bold"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            <span>{{ t('fm_new_file') || 'New File' }}</span>
          </button>
          <!-- + New Folder -->
          <button
            type="button"
            @click="showNewDirDialog = true"
            class="px-2.5 py-1 rounded bg-gray-900 hover:bg-cyan-950 text-cyan-300 border border-cyan-800 hover:border-cyan-500 transition flex items-center gap-1 cursor-pointer font-bold"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
              <line x1="12" y1="10" x2="12" y2="16"/>
              <line x1="9" y1="13" x2="15" y2="13"/>
            </svg>
            <span>{{ t('fm_new_dir') || 'New Folder' }}</span>
          </button>
          <!-- Upload File -->
          <button
            type="button"
            @click="openUploadModal"
            class="px-2.5 py-1 rounded bg-gray-900 hover:bg-cyan-950 text-cyan-300 border border-cyan-800 hover:border-cyan-500 transition flex items-center gap-1 cursor-pointer font-bold"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <span>{{ t('fm_upload_file') || 'Upload File' }}</span>
          </button>
          <!-- Paste (visible when clipboard has items) -->
          <button
            v-if="clipboard && clipboard.items && clipboard.items.length > 0"
            type="button"
            @click="pasteClipboard"
            class="px-2.5 py-1 rounded bg-cyan-900/80 hover:bg-cyan-800 text-cyan-200 border border-cyan-500 transition flex items-center gap-1 cursor-pointer font-bold"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
              <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
            </svg>
            <span>{{ t('fm_paste') || 'Paste' }} ({{ clipboard.items.length }})</span>
          </button>
        </div>

        <div class="flex items-center gap-2">
          <!-- Filter input -->
          <div class="relative flex items-center">
            <input
              v-model="searchFilter"
              type="text"
              placeholder="Filter files..."
              class="w-48 bg-[#020409] border border-cyan-900 focus:border-cyan-400 rounded px-2.5 py-1 text-xs text-gray-100 placeholder-gray-500 focus:outline-none transition"
            />
            <button
              v-if="searchFilter"
              @click="searchFilter = ''"
              class="absolute right-2 text-gray-500 hover:text-gray-300 text-xs cursor-pointer"
            >
              ✕
            </button>
          </div>
          <!-- Auto .bak Badge -->
          <span class="text-[10px] text-amber-400 font-bold px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800/60 hidden sm:inline select-none">
            AUTO .bak ENABLED
          </span>
        </div>
      </div>

      <!-- Floating Clipboard Bar -->
      <div
        v-if="clipboard && clipboard.items && clipboard.items.length > 0"
        class="bg-cyan-950/60 border-b border-cyan-500/30 px-3 py-1.5 flex items-center justify-between text-xs transition"
      >
        <div class="flex items-center gap-2">
          <span class="font-bold text-cyan-300">
            {{ clipboard.items.length }} {{ t('fm_ready_to_paste') || 'item(s) ready to paste' }}
            <span class="text-cyan-400/70 font-mono text-[11px]">({{ clipboard.mode === 'cut' ? 'cut' : 'copied' }})</span>
          </span>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            @click="pasteClipboard"
            class="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold cursor-pointer transition text-xs flex items-center gap-1"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
              <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
            </svg>
            <span>{{ t('fm_paste_here') || 'Paste Here' }}</span>
          </button>
          <button
            type="button"
            @click="clearClipboard"
            class="px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 cursor-pointer text-xs"
          >
            {{ t('fm_cancel') || 'Cancel' }}
          </button>
        </div>
      </div>

      <!-- Bulk Action Bar (when items are selected) -->
      <div
        v-if="selectedPaths.length > 0"
        class="bg-cyan-950/40 border-b border-cyan-500/40 px-3 py-1.5 flex items-center justify-between text-xs transition"
      >
        <div class="flex items-center gap-2">
          <span class="font-bold text-cyan-300">{{ selectedPaths.length }} items selected</span>
          <button
            @click="clearSelection"
            class="text-[11px] text-gray-400 hover:text-gray-200 underline cursor-pointer"
          >
            Clear (Esc)
          </button>
        </div>
        <div class="flex items-center gap-2">
          <button
            @click="confirmBulkDelete"
            class="px-2.5 py-1 rounded bg-rose-950 text-rose-300 border border-rose-800 hover:bg-rose-900 cursor-pointer font-bold text-xs transition"
          >
            Delete Selected
          </button>
        </div>
      </div>

      <!-- Feedback Notification Toast -->
      <div
        v-if="feedbackMsg"
        class="mx-3 mt-2 px-3 py-1.5 rounded text-xs flex items-center justify-between border"
        :class="feedbackMsg.type === 'error' ? 'bg-rose-950/80 border-rose-800 text-rose-300' : 'bg-emerald-950/80 border-emerald-800 text-emerald-300'"
      >
        <span>{{ feedbackMsg.text }}</span>
        <button @click="feedbackMsg = null" class="text-xs ml-2 cursor-pointer">✕</button>
      </div>

      <!-- Directory Items Table (Canon ~/rj45 table structure) -->
      <div class="flex-1 overflow-y-auto p-3 select-text">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider sticky top-0 bg-[#070b16] select-none z-10">
            <tr>
              <th class="py-2 px-3 w-8 text-center">
                <input
                  type="checkbox"
                  :checked="isAllSelected"
                  @change="toggleSelectAll"
                  class="cursor-pointer accent-cyan-500 rounded"
                  title="Select All"
                />
              </th>
              <th class="py-2 px-3">{{ t('fm_col_name') || 'Name' }}</th>
              <th class="py-2 px-3">{{ t('fm_col_size') || 'Size' }}</th>
              <th class="py-2 px-3">{{ t('fm_col_perms') || 'Permissions' }}</th>
              <th class="py-2 px-3">{{ t('fm_col_owner') || 'Owner : Group' }}</th>
              <th class="py-2 px-3">{{ t('fm_col_mtime') || 'Modified' }}</th>
              <th class="py-2 px-3 text-center w-24">{{ t('fm_col_actions') || 'Actions' }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <!-- Row: .. (Parent Directory) when currentPath !== '/' -->
            <tr
              v-if="currentPath !== '/' && currentPath !== ''"
              class="hover:bg-cyan-950/20 transition cursor-pointer"
              @click="navigateUp"
            >
              <td class="py-2 px-3 text-center text-gray-600">-</td>
              <td colspan="6" class="py-2 px-3 font-semibold text-gray-400 hover:text-cyan-300 flex items-center gap-2">
                <svg class="w-4 h-4 text-cyan-500/70 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
                </svg>
                <span>{{ t('fm_parent_dir') || '.. (Parent Directory)' }}</span>
              </td>
            </tr>

            <!-- File and Folder Items -->
            <tr
              v-for="item in filteredItems"
              :key="item.path || item.name"
              class="hover:bg-cyan-950/20 transition group"
              :class="{ 'bg-cyan-950/30': isSelected(item.path), 'opacity-40': isCut(item.path) }"
            >
              <!-- Checkbox -->
              <td class="py-2 px-3 text-center" @click.stop>
                <input
                  type="checkbox"
                  :checked="isSelected(item.path)"
                  @change="toggleSelect(item.path)"
                  class="cursor-pointer accent-cyan-500 rounded"
                />
              </td>

              <!-- Nama & Icon: clicking folder navigates in; clicking file opens editor -->
              <td
                class="py-2 px-3 font-semibold flex items-center gap-2 cursor-pointer"
                @click="handleItemClick(item)"
              >
                <!-- Folder Icon -->
                <svg v-if="item.is_dir" class="w-4 h-4 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
                </svg>
                <!-- File Icon -->
                <svg v-else class="w-4 h-4 text-gray-400 shrink-0 group-hover:text-cyan-300 transition" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>
                <span :class="item.is_dir ? 'text-cyan-300 font-bold' : 'text-gray-200'">{{ item.name }}</span>
              </td>

              <!-- Ukuran (Size): '-' for directory, human size for file -->
              <td class="py-2 px-3 text-gray-300 font-mono text-[11px]">
                {{ item.is_dir ? '—' : (item.size_human || item.size) }}
              </td>

              <!-- Izin (Permissions) -->
              <td class="py-2 px-3 text-gray-400 font-mono text-[11px]">{{ item.perms }}</td>

              <!-- Pemilik : Grup -->
              <td class="py-2 px-3 text-gray-400 font-mono text-[11px]">{{ item.owner }}</td>

              <!-- Waktu Diubah (Modified Date) -->
              <td class="py-2 px-3 text-gray-400 font-mono text-[11px]">{{ item.mtime }}</td>

              <!-- Tindakan: Sleek 3-Dots Dropdown Menu -->
              <td class="py-2 px-3 text-center" @click.stop>
                <div class="relative inline-block text-left noc-act-dropdown">
                  <button
                    type="button"
                    @click.stop="toggleDropdown(item.path, $event)"
                    class="w-7 h-7 inline-flex items-center justify-center rounded text-gray-400 hover:text-cyan-300 hover:bg-cyan-950/80 border border-gray-800/80 hover:border-cyan-500/50 transition cursor-pointer"
                    :title="t('fm_col_actions') || 'Actions'"
                    aria-label="Actions"
                  >
                    <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
                      <circle cx="19" cy="12" r="1.5" fill="currentColor"/>
                      <circle cx="5" cy="12" r="1.5" fill="currentColor"/>
                    </svg>
                  </button>

                  <!-- Dropdown Menu with Smart Drop-Up/Drop-Down (Teleported to body to eliminate modal clipping) -->
                  <Teleport to="body">
                    <div
                      v-if="activeDropdownPath === item.path"
                      class="noc-act-dropdown-menu fixed z-[100005] bg-[#0c1328] border border-cyan-500/50 rounded shadow-2xl py-1 text-xs w-44 font-sans overflow-y-auto scrollbar-thin"
                      :style="dropdownPositionStyle"
                      @click.stop
                    >
                    <!-- File Actions -->
                    <template v-if="!item.is_dir">
                      <button
                        type="button"
                        @click="openEditor(item); closeDropdown()"
                        class="w-full text-left px-3 py-1.5 hover:bg-cyan-950 text-cyan-200 hover:text-white flex items-center gap-2 cursor-pointer"
                      >
                        <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                        </svg>
                        <span>{{ t('fm_view_edit') || 'View & Edit' }}</span>
                      </button>
                      <button
                        type="button"
                        @click="downloadFile(item); closeDropdown()"
                        class="w-full text-left px-3 py-1.5 hover:bg-cyan-950 text-gray-200 hover:text-white flex items-center gap-2 cursor-pointer"
                      >
                        <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                          <polyline points="7 10 12 15 17 10"/>
                          <line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        <span>{{ t('fm_download') || 'Download' }}</span>
                      </button>
                      <div class="border-t border-gray-800 my-1"></div>
                    </template>

                    <!-- Directory-specific Actions: Open in Terminal -->
                    <template v-else>
                      <button
                        type="button"
                        @click="openTerminalAtFolder(item); closeDropdown()"
                        class="w-full text-left px-3 py-1.5 hover:bg-cyan-950 text-cyan-200 hover:text-white flex items-center gap-2 cursor-pointer"
                      >
                        <svg class="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="4 17 10 11 4 5"/>
                          <line x1="12" y1="19" x2="20" y2="19"/>
                        </svg>
                        <span>{{ t('fm_open_terminal') || 'Open in Terminal' }}</span>
                      </button>
                      <div class="border-t border-gray-800 my-1"></div>
                    </template>

                    <!-- Common Actions (File & Directory) -->
                    <button
                      type="button"
                      @click="copyItem(item); closeDropdown()"
                      class="w-full text-left px-3 py-1.5 hover:bg-cyan-950 text-gray-200 hover:text-white flex items-center gap-2 cursor-pointer"
                    >
                      <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
                        <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
                      </svg>
                      <span>{{ t('fm_copy') || 'Copy' }}</span>
                    </button>
                    <button
                      type="button"
                      @click="openDuplicateModal(item); closeDropdown()"
                      class="w-full text-left px-3 py-1.5 hover:bg-cyan-950 text-gray-200 hover:text-white flex items-center gap-2 cursor-pointer"
                    >
                      <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M15 12l5 5m-5 0 5-5"/>
                        <rect width="12" height="12" x="2" y="2" rx="2"/>
                      </svg>
                      <span>{{ t('fm_duplicate') || 'Duplicate' }}</span>
                    </button>
                    <button
                      type="button"
                      @click="cutItem(item); closeDropdown()"
                      class="w-full text-left px-3 py-1.5 hover:bg-cyan-950 text-gray-200 hover:text-white flex items-center gap-2 cursor-pointer"
                    >
                      <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="6" cy="6" r="3"/>
                        <circle cx="6" cy="18" r="3"/>
                        <line x1="20" y1="4" x2="8.12" y2="15.88"/>
                        <line x1="14.47" y1="14.48" x2="20" y2="20"/>
                        <line x1="8.12" y1="8.12" x2="12" y2="12"/>
                      </svg>
                      <span>{{ t('fm_cut') || 'Cut' }}</span>
                    </button>
                    <button
                      type="button"
                      @click="openChmodModal(item); closeDropdown()"
                      class="w-full text-left px-3 py-1.5 hover:bg-cyan-950 text-gray-200 hover:text-white flex items-center gap-2 cursor-pointer"
                    >
                      <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                      </svg>
                      <span>{{ t('fm_permissions') || 'Permissions' }}</span>
                    </button>
                    <button
                      type="button"
                      @click="openRenameModal(item); closeDropdown()"
                      class="w-full text-left px-3 py-1.5 hover:bg-cyan-950 text-gray-200 hover:text-white flex items-center gap-2 cursor-pointer"
                    >
                      <svg class="w-3.5 h-3.5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                      </svg>
                      <span>{{ t('fm_rename') || 'Rename' }}</span>
                    </button>
                    <div class="border-t border-gray-800 my-1"></div>
                    <button
                      type="button"
                      @click="confirmDeleteItem(item); closeDropdown()"
                      class="w-full text-left px-3 py-1.5 hover:bg-rose-950/80 text-rose-400 hover:text-rose-200 flex items-center gap-2 cursor-pointer"
                    >
                      <svg class="w-3.5 h-3.5 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                      </svg>
                      <span>{{ t('fm_delete') || 'Delete' }}</span>
                    </button>
                  </div>
                  </Teleport>
                </div>
              </td>
            </tr>

            <!-- Empty / No Items row -->
            <tr v-if="filteredItems.length === 0 && !loading">
              <td colspan="7" class="py-8 text-center text-gray-500 italic">
                {{ searchFilter ? 'No matching files found' : (t('fm_empty_dir') || 'This directory is empty.') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Status Bar Footer -->
      <div class="bg-[#050811] border-t border-cyan-500/20 px-3 py-1 flex items-center justify-between text-[11px] text-gray-400 select-none">
        <div class="flex items-center gap-2">
          <span>{{ summaryStats }}</span>
        </div>
        <div class="flex items-center gap-2 text-cyan-400/80 font-mono">
          <span>Path: {{ currentPath }}</span>
        </div>
      </div>

      <!-- MODAL: NEW FILE PROMPT -->
      <div
        v-if="showNewFileDialog"
        class="absolute inset-0 bg-black/75 z-30 flex items-center justify-center p-4"
        @click.self="showNewFileDialog = false"
      >
        <div class="bg-[#0b1226] border border-cyan-500/60 rounded-lg p-5 w-full max-w-sm flex flex-col space-y-3 shadow-2xl">
          <div class="text-xs font-bold text-cyan-300 flex items-center gap-2">
            <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            <span>Create New File</span>
          </div>
          <div class="text-[11px] text-gray-400">
            Inside: <span class="font-mono text-cyan-200">{{ currentPath }}</span>
          </div>
          <input
            v-model="newFileName"
            type="text"
            placeholder="filename.txt"
            class="bg-[#030612] border border-cyan-900 rounded px-3 py-1.5 text-xs text-gray-100 focus:outline-none focus:border-cyan-400 font-mono"
            @keydown.enter="submitNewFile"
            autofocus
          />
          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              @click="showNewFileDialog = false"
              class="px-3 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 text-xs cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              @click="submitNewFile"
              class="px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs cursor-pointer"
            >
              Create
            </button>
          </div>
        </div>
      </div>

      <!-- MODAL: NEW FOLDER PROMPT -->
      <div
        v-if="showNewDirDialog"
        class="absolute inset-0 bg-black/75 z-30 flex items-center justify-center p-4"
        @click.self="showNewDirDialog = false"
      >
        <div class="bg-[#0b1226] border border-cyan-500/60 rounded-lg p-5 w-full max-w-sm flex flex-col space-y-3 shadow-2xl">
          <div class="text-xs font-bold text-cyan-300 flex items-center gap-2">
            <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
              <line x1="12" y1="10" x2="12" y2="16"/>
              <line x1="9" y1="13" x2="15" y2="13"/>
            </svg>
            <span>Create New Folder</span>
          </div>
          <div class="text-[11px] text-gray-400">
            Inside: <span class="font-mono text-cyan-200">{{ currentPath }}</span>
          </div>
          <input
            v-model="newDirName"
            type="text"
            placeholder="folder_name"
            class="bg-[#030612] border border-cyan-900 rounded px-3 py-1.5 text-xs text-gray-100 focus:outline-none focus:border-cyan-400 font-mono"
            @keydown.enter="submitNewDir"
            autofocus
          />
          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              @click="showNewDirDialog = false"
              class="px-3 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 text-xs cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              @click="submitNewDir"
              class="px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs cursor-pointer"
            >
              Create
            </button>
          </div>
        </div>
      </div>

      <!-- MODAL: RENAME PROMPT -->
      <div
        v-if="itemToRename"
        class="absolute inset-0 bg-black/75 z-30 flex items-center justify-center p-4"
        @click.self="itemToRename = null"
      >
        <div class="bg-[#0b1226] border border-cyan-500/60 rounded-lg p-5 w-full max-w-sm flex flex-col space-y-3 shadow-2xl">
          <div class="text-xs font-bold text-cyan-300 flex items-center gap-2">
            <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            <span>Rename {{ itemToRename.is_dir ? 'Folder' : 'File' }}</span>
          </div>
          <div class="text-[11px] text-gray-400 truncate">
            Current: <span class="font-mono text-cyan-200">{{ itemToRename.name }}</span>
          </div>
          <input
            v-model="renameNewName"
            type="text"
            class="bg-[#030612] border border-cyan-900 rounded px-3 py-1.5 text-xs text-gray-100 focus:outline-none focus:border-cyan-400 font-mono"
            @keydown.enter="submitRename"
            autofocus
          />
          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              @click="itemToRename = null"
              class="px-3 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 text-xs cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              @click="submitRename"
              class="px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs cursor-pointer"
            >
              Rename
            </button>
          </div>
        </div>
      </div>

      <!-- MODAL: CHMOD PROMPT -->
      <div
        v-if="itemToChmod"
        class="absolute inset-0 bg-black/75 z-30 flex items-center justify-center p-4"
        @click.self="itemToChmod = null"
      >
        <div class="bg-[#0b1226] border border-cyan-500/60 rounded-lg p-5 w-full max-w-sm flex flex-col space-y-3 shadow-2xl">
          <div class="text-xs font-bold text-cyan-300 flex items-center gap-2">
            <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <span>Change Permissions (chmod)</span>
          </div>
          <div class="text-[11px] text-gray-400 truncate">
            Target: <span class="font-mono text-cyan-200">{{ itemToChmod.name }}</span>
          </div>
          <div class="flex items-center gap-2">
            <label class="text-xs text-gray-300">Octal Mode:</label>
            <input
              v-model="chmodOctalMode"
              type="text"
              placeholder="0644"
              class="w-24 bg-[#030612] border border-cyan-900 rounded px-2.5 py-1 text-xs text-gray-100 focus:outline-none focus:border-cyan-400 font-mono"
              @keydown.enter="submitChmod"
              autofocus
            />
            <span class="text-[11px] text-gray-500 font-mono">e.g. 0644, 0755</span>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              @click="itemToChmod = null"
              class="px-3 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 text-xs cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              @click="submitChmod"
              class="px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs cursor-pointer"
            >
              Update Mode
            </button>
          </div>
        </div>
      </div>

      <!-- MODAL: DELETE CONFIRMATION -->
      <div
        v-if="itemToDelete"
        class="absolute inset-0 bg-black/75 z-30 flex items-center justify-center p-4"
        @click.self="itemToDelete = null"
      >
        <div class="bg-[#130d14] border border-rose-500/60 rounded-lg p-5 w-full max-w-sm flex flex-col space-y-3 shadow-2xl">
          <div class="text-xs font-bold text-rose-400 flex items-center gap-2">
            <svg class="w-4 h-4 text-rose-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <span>Confirm Deletion</span>
          </div>
          <div class="text-xs text-gray-300">
            Are you sure you want to delete this {{ itemToDelete.is_dir ? 'folder and all its contents' : 'file' }}?
          </div>
          <div class="font-mono text-xs text-rose-300 bg-rose-950/40 p-2 rounded border border-rose-900 break-all">
            {{ itemToDelete.path }}
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              @click="itemToDelete = null"
              class="px-3 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 text-xs cursor-pointer"
            >
              {{ t('fm_cancel') || 'Cancel' }}
            </button>
            <button
              type="button"
              @click="executeDeleteItem"
              class="px-3 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs cursor-pointer"
            >
              Delete Permanently
            </button>
          </div>
        </div>
      </div>

      <!-- MODAL: DUPLICATE PROMPT -->
      <div
        v-if="itemToDuplicate"
        class="absolute inset-0 bg-black/75 z-30 flex items-center justify-center p-4"
        @click.self="itemToDuplicate = null"
      >
        <div class="bg-[#0b1226] border border-cyan-500/60 rounded-lg p-5 w-full max-w-sm flex flex-col space-y-3 shadow-2xl">
          <div class="text-xs font-bold text-cyan-300 flex items-center gap-2">
            <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M15 12l5 5m-5 0 5-5"/>
              <rect width="12" height="12" x="2" y="2" rx="2"/>
            </svg>
            <span>{{ t('fm_duplicate_title') || 'Duplicate File / Folder' }}</span>
          </div>
          <div class="text-[11px] text-gray-400 truncate">
            Source: <span class="font-mono text-cyan-200">{{ itemToDuplicate.name }}</span>
          </div>
          <input
            v-model="duplicateNewName"
            type="text"
            class="bg-[#030612] border border-cyan-900 rounded px-3 py-1.5 text-xs text-gray-100 focus:outline-none focus:border-cyan-400 font-mono"
            @keydown.enter="submitDuplicate"
            autofocus
          />
          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              @click="itemToDuplicate = null"
              class="px-3 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 text-xs cursor-pointer"
            >
              {{ t('fm_cancel') || 'Cancel' }}
            </button>
            <button
              type="button"
              @click="submitDuplicate"
              class="px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs cursor-pointer"
            >
              {{ t('fm_duplicate') || 'Duplicate' }}
            </button>
          </div>
        </div>
      </div>

      <!-- MODAL: UPLOAD FILE -->
      <div
        v-if="showUploadDialog"
        class="absolute inset-0 bg-black/75 z-30 flex items-center justify-center p-4"
        @click.self="showUploadDialog = false"
      >
        <div class="bg-[#0b1226] border border-cyan-500/60 rounded-lg p-5 w-full max-w-sm flex flex-col space-y-3 shadow-2xl">
          <div class="text-xs font-bold text-cyan-300 flex items-center gap-2">
            <svg class="w-4 h-4 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <span>{{ t('fm_upload_title') || 'Upload File to Server' }}</span>
          </div>
          <div class="text-[11px] text-gray-400">
            Destination: <span class="font-mono text-cyan-200">{{ currentPath }}</span>
          </div>
          <div class="border-2 border-dashed border-gray-700 hover:border-cyan-500/60 rounded p-4 text-center cursor-pointer bg-[#02040a]">
            <input
              type="file"
              ref="uploadFileInputRef"
              @change="onFileSelected"
              class="text-xs text-gray-300 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-cyan-950 file:text-cyan-300 cursor-pointer w-full"
            />
          </div>
          <div v-if="selectedUploadFile" class="text-[11px] text-gray-300 font-mono truncate">
            {{ selectedUploadFile.name }} ({{ selectedUploadFile.size }} bytes)
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              @click="showUploadDialog = false"
              class="px-3 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 text-xs cursor-pointer"
            >
              {{ t('fm_cancel') || 'Cancel' }}
            </button>
            <button
              type="button"
              @click="submitUpload"
              :disabled="!selectedUploadFile || uploading"
              class="px-3 py-1 rounded bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold text-xs cursor-pointer flex items-center gap-1"
            >
              <span>{{ uploading ? 'Uploading...' : (t('fm_upload') || 'Upload') }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- INTEGRATED FILE TEXT EDITOR OVERLAY -->
      <div
        v-if="editingFile"
        class="absolute inset-0 bg-[#060a15] z-40 flex flex-col p-4 space-y-2 select-text"
        @keydown.ctrl.s.prevent="saveEditor"
        @keydown.meta.s.prevent="saveEditor"
      >
        <!-- Editor Header -->
        <div class="flex items-center justify-between border-b border-cyan-500/30 pb-2 select-none">
          <div class="flex items-center gap-2 min-w-0">
            <svg class="w-4 h-4 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
            </svg>
            <span class="text-xs font-bold text-cyan-300 font-mono truncate">
              // EDITOR: {{ editingFile.name }}
            </span>
            <span class="text-[10px] text-emerald-400 font-mono bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-800 hidden sm:inline shrink-0">
              auto .bak backup
            </span>
            <span class="text-[10px] text-gray-400 font-mono hidden md:inline shrink-0">
              Lines: {{ editorLineCount }} · Chars: {{ editorContent.length }}
            </span>
          </div>

          <!-- Editor Actions -->
          <div class="flex items-center gap-2 shrink-0">
            <button
              type="button"
              @click="saveEditor"
              class="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded text-xs cursor-pointer flex items-center gap-1.5 transition"
              :disabled="savingFile"
            >
              <svg v-if="!savingFile" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <polyline points="17 21 17 13 7 13 7 21"/>
                <polyline points="7 3 7 8 15 8"/>
              </svg>
              <span>{{ savingFile ? 'Saving...' : 'Save (Ctrl+S)' }}</span>
            </button>
            <button
              type="button"
              @click="closeEditor"
              class="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded text-xs cursor-pointer transition"
            >
              Close
            </button>
          </div>
        </div>

        <!-- Editor Textarea -->
        <textarea
          v-model="editorContent"
          class="flex-1 w-full bg-[#03050a] border border-cyan-900/80 rounded p-3 text-xs font-mono text-gray-100 focus:outline-none focus:border-cyan-400 resize-none leading-relaxed tab-4"
          spellcheck="false"
          placeholder="File content..."
        ></textarea>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from '../../i18n'
import { confirmAction } from '../../utils/useToast'

const { t } = useI18n()

const props = defineProps({
  open: { type: Boolean, default: false },
  server: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['close', 'open-terminal'])

// Window state
const isFullWindow = ref(false)
const isFullscreen = ref(false)

// Navigation state
const currentPath = ref('/root')
const loading = ref(false)
const items = ref([])
const searchFilter = ref('')
const historyStack = ref([])
const historyIndex = ref(-1)

// Selection state
const selectedPaths = ref([])

// Address bar manual input
const isManualPathInput = ref(false)
const manualPathInputValue = ref('')
const manualPathInputRef = ref(null)

// Actions & Dialogs state
const showNewFileDialog = ref(false)
const newFileName = ref('')
const showNewDirDialog = ref(false)
const newDirName = ref('')
const itemToRename = ref(null)
const renameNewName = ref('')
const itemToChmod = ref(null)
const chmodOctalMode = ref('0644')
const itemToDelete = ref(null)
const feedbackMsg = ref(null)

// Dropdown Action Menu state
const activeDropdownPath = ref(null)
const dropdownPositionStyle = ref({})

// Editor state
const editingFile = ref(null)
const editorContent = ref('')
const savingFile = ref(false)

// Dynamic bookmarks physically discovered from server
const bookmarks = ref([])

// Clipboard state (copy / cut / paste)
const clipboard = ref(null) // { mode: 'copy'|'cut', items: string[], sourceDir: string }

// Duplicate Modal state
const itemToDuplicate = ref(null)
const duplicateNewName = ref('')

// Upload Modal state
const showUploadDialog = ref(false)
const selectedUploadFile = ref(null)
const uploadFileInputRef = ref(null)
const uploading = ref(false)

const breadcrumbSegments = computed(() => {
  if (!currentPath.value || currentPath.value === '/') return []
  const parts = currentPath.value.split('/').filter(Boolean)
  let accum = ''
  return parts.map(p => {
    accum += '/' + p
    return { name: p, path: accum }
  })
})

const filteredItems = computed(() => {
  // Exclude raw .. if returned from backend, since we handle Parent row explicitly at top
  const list = items.value.filter(i => i.name !== '.. (parent)' && i.name !== '..')
  if (!searchFilter.value) return list
  const q = searchFilter.value.toLowerCase()
  return list.filter(i => i.name.toLowerCase().includes(q))
})

const isAllSelected = computed(() => {
  if (filteredItems.value.length === 0) return false
  return filteredItems.value.every(i => selectedPaths.value.includes(i.path))
})

const summaryStats = computed(() => {
  const dirs = filteredItems.value.filter(i => i.is_dir).length
  const files = filteredItems.value.filter(i => !i.is_dir).length
  return `${filteredItems.value.length} items (${dirs} folders, ${files} files)`
})

const editorLineCount = computed(() => {
  return (editorContent.value.match(/\n/g) || []).length + 1
})

function notify(text, type = 'success') {
  feedbackMsg.value = { text, type }
  setTimeout(() => {
    if (feedbackMsg.value?.text === text) feedbackMsg.value = null
  }, 3500)
}

function copyIp(ip) {
  if (!ip) return
  navigator.clipboard.writeText(ip).then(() => {
    notify(`IP ${ip} copied to clipboard!`)
  })
}

function handleEsc() {
  if (editingFile.value) {
    closeEditor()
  } else if (activeDropdownPath.value) {
    closeDropdown()
  } else if (itemToDuplicate.value) {
    itemToDuplicate.value = null
  } else if (showUploadDialog.value) {
    showUploadDialog.value = false
  } else if (itemToRename.value) {
    itemToRename.value = null
  } else if (itemToChmod.value) {
    itemToChmod.value = null
  } else if (showNewFileDialog.value) {
    showNewFileDialog.value = false
  } else if (showNewDirDialog.value) {
    showNewDirDialog.value = false
  } else if (itemToDelete.value) {
    itemToDelete.value = null
  } else if (selectedPaths.value.length > 0) {
    clearSelection()
  } else {
    emit('close')
  }
}

// Selection handling
function isSelected(path) {
  return selectedPaths.value.includes(path)
}

function toggleSelect(path) {
  const idx = selectedPaths.value.indexOf(path)
  if (idx >= 0) {
    selectedPaths.value.splice(idx, 1)
  } else {
    selectedPaths.value.push(path)
  }
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    selectedPaths.value = []
  } else {
    selectedPaths.value = filteredItems.value.map(i => i.path)
  }
}

function clearSelection() {
  selectedPaths.value = []
}

// Dropdown Action Menu with Dynamic Drop-Up / Drop-Down
function toggleDropdown(path, event) {
  if (activeDropdownPath.value === path) {
    closeDropdown()
    return
  }
  activeDropdownPath.value = path
  if (event && event.currentTarget) {
    const rect = event.currentTarget.getBoundingClientRect()
    const spaceBelow = window.innerHeight - rect.bottom
    const spaceAbove = rect.top
    const estimatedMenuHeight = 310

    // If space below is insufficient and space above has more room, open upwards!
    if (spaceBelow < estimatedMenuHeight && spaceAbove > spaceBelow) {
      dropdownPositionStyle.value = {
        bottom: `${window.innerHeight - rect.top + 4}px`,
        right: `${Math.max(8, window.innerWidth - rect.right)}px`,
        maxHeight: `${Math.min(420, spaceAbove - 16)}px`
      }
    } else {
      dropdownPositionStyle.value = {
        top: `${rect.bottom + 4}px`,
        right: `${Math.max(8, window.innerWidth - rect.right)}px`,
        maxHeight: `${Math.min(420, spaceBelow - 16)}px`
      }
    }
  }
}

function closeDropdown() {
  activeDropdownPath.value = null
}

function handleClickOutside(e) {
  if (activeDropdownPath.value && !e.target.closest('.noc-act-dropdown') && !e.target.closest('.noc-act-dropdown-menu')) {
    closeDropdown()
  }
}

// Clipboard methods (Copy / Cut / Paste)
function copyItem(item) {
  clipboard.value = {
    mode: 'copy',
    items: [item.path],
    sourceDir: currentPath.value
  }
  notify(`Copied to clipboard: ${item.name}`)
}

function cutItem(item) {
  clipboard.value = {
    mode: 'cut',
    items: [item.path],
    sourceDir: currentPath.value
  }
  notify(`Cut to clipboard: ${item.name}`)
}

function isCut(path) {
  return clipboard.value?.mode === 'cut' && clipboard.value?.items?.includes(path)
}

function clearClipboard() {
  clipboard.value = null
}

async function pasteClipboard() {
  if (!clipboard.value || !clipboard.value.items || clipboard.value.items.length === 0) return
  const isCutMode = clipboard.value.mode === 'cut'
  const endpoint = isCutMode ? `/api/servers/${props.server.id}/files/move` : `/api/servers/${props.server.id}/files/copy`
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        sources: clipboard.value.items,
        destination: currentPath.value
      })
    })
    const data = await res.json()
    if (data.ok) {
      notify(`Pasted ${clipboard.value.items.length} item(s) successfully`)
      if (isCutMode) {
        clipboard.value = null
      }
      await loadDirectory(currentPath.value, false)
    } else {
      notify(data.detail || 'Failed to paste items', 'error')
    }
  } catch (err) {
    notify('Error pasting items: ' + err.message, 'error')
  }
}

// Duplicate methods
function openDuplicateModal(item) {
  itemToDuplicate.value = item
  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  const ts = `${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}`
  if (!item.is_dir && item.name.includes('.') && !item.name.startsWith('.')) {
    const lastDot = item.name.lastIndexOf('.')
    const base = item.name.substring(0, lastDot)
    const ext = item.name.substring(lastDot)
    duplicateNewName.value = `${base}_${ts}${ext}`
  } else {
    duplicateNewName.value = `${item.name}_${ts}`
  }
}

async function submitDuplicate() {
  if (!itemToDuplicate.value) return
  const targetName = duplicateNewName.value.trim()
  if (!targetName) return
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/duplicate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        source: itemToDuplicate.value.path,
        target_name: targetName
      })
    })
    const data = await res.json()
    if (data.ok) {
      notify(`Duplicated to ${targetName}`)
      itemToDuplicate.value = null
      await loadDirectory(currentPath.value, false)
    } else {
      notify(data.detail || 'Failed to duplicate item', 'error')
    }
  } catch (err) {
    notify('Error duplicating: ' + err.message, 'error')
  }
}

// Upload methods
function openUploadModal() {
  selectedUploadFile.value = null
  showUploadDialog.value = true
}

function onFileSelected(e) {
  const files = e.target.files
  if (files && files.length > 0) {
    selectedUploadFile.value = files[0]
  }
}

async function submitUpload() {
  if (!selectedUploadFile.value) return
  uploading.value = true
  const token = localStorage.getItem('pantau_token')
  const formData = new FormData()
  formData.append('destination', currentPath.value)
  formData.append('file', selectedUploadFile.value)

  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/upload`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`
      },
      body: formData
    })
    const data = await res.json()
    if (data.ok) {
      notify(`Uploaded ${selectedUploadFile.value.name} successfully`)
      showUploadDialog.value = false
      selectedUploadFile.value = null
      await loadDirectory(currentPath.value, false)
    } else {
      notify(data.detail || 'Failed to upload file', 'error')
    }
  } catch (err) {
    notify('Error uploading file: ' + err.message, 'error')
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  window.addEventListener('click', handleClickOutside)
  window.addEventListener('scroll', closeDropdown, true)
  window.addEventListener('resize', closeDropdown)
})

onUnmounted(() => {
  window.removeEventListener('click', handleClickOutside)
  window.removeEventListener('scroll', closeDropdown, true)
  window.removeEventListener('resize', closeDropdown)
})

async function loadDirectory(path = currentPath.value, pushToHistory = true) {
  if (!props.server?.id) return
  loading.value = true
  closeDropdown()
  selectedPaths.value = []
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}/files?path=${encodeURIComponent(path)}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    const data = await res.json()
    if (data.ok) {
      currentPath.value = data.path
      items.value = data.items || []
      isManualPathInput.value = false
      if (data.bookmarks && Array.isArray(data.bookmarks)) {
        bookmarks.value = data.bookmarks
      }
      if (pushToHistory) {
        if (historyIndex.value < historyStack.value.length - 1) {
          historyStack.value = historyStack.value.slice(0, historyIndex.value + 1)
        }
        historyStack.value.push(data.path)
        historyIndex.value = historyStack.value.length - 1
      }
    } else {
      notify(data.detail || 'Failed to list directory', 'error')
    }
  } catch (err) {
    notify('Network error: ' + err.message, 'error')
  } finally {
    loading.value = false
  }
}

function goBack() {
  if (historyIndex.value > 0) {
    historyIndex.value--
    loadDirectory(historyStack.value[historyIndex.value], false)
  }
}

function goForward() {
  if (historyIndex.value < historyStack.value.length - 1) {
    historyIndex.value++
    loadDirectory(historyStack.value[historyIndex.value], false)
  }
}

function navigateUp() {
  if (currentPath.value === '/' || !currentPath.value) return
  const parts = currentPath.value.split('/').filter(Boolean)
  parts.pop()
  const parent = '/' + parts.join('/')
  loadDirectory(parent)
}

function refreshCurrent() {
  loadDirectory(currentPath.value, false)
}

function toggleManualPathInput() {
  isManualPathInput.value = !isManualPathInput.value
  if (isManualPathInput.value) {
    manualPathInputValue.value = currentPath.value
    nextTick(() => manualPathInputRef.value?.focus())
  }
}

function submitManualPath() {
  const path = manualPathInputValue.value.trim()
  if (path) {
    loadDirectory(path)
  }
}

function emitTerminalAtPath() {
  notify(`Launching Web Terminal at ${currentPath.value}...`, 'success')
  emit('open-terminal', {
    ...props.server,
    workingDirectory: currentPath.value
  })
}

function openTerminalAtFolder(item) {
  notify(`Launching Web Terminal at ${item.path}...`, 'success')
  emit('open-terminal', {
    ...props.server,
    workingDirectory: item.path
  })
}

function popoutWindow() {
  window.open(
    `/?standalone=files&sid=${props.server.id}`,
    `pantau_fm_${props.server.id}`,
    'popup=yes,width=1220,height=820,menubar=no,toolbar=no,status=no'
  )
}

// Navigating via click: clicking folder enters directory; clicking file opens editor
function handleItemClick(item) {
  if (item.is_dir) {
    loadDirectory(item.path)
  } else {
    openEditor(item)
  }
}

async function submitNewFile() {
  const name = newFileName.value.trim()
  if (!name) return
  const token = localStorage.getItem('pantau_token')
  const newPath = (currentPath.value.endsWith('/') ? currentPath.value : currentPath.value + '/') + name
  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/touch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ path: newPath })
    })
    const data = await res.json()
    if (data.ok) {
      showNewFileDialog.value = false
      newFileName.value = ''
      notify(`File ${name} created`)
      await loadDirectory(currentPath.value, false)
      openEditor({ name, path: newPath, is_dir: false })
    } else {
      notify(data.detail || 'Failed to create file', 'error')
    }
  } catch (err) {
    notify('Error creating file: ' + err.message, 'error')
  }
}

async function submitNewDir() {
  const name = newDirName.value.trim()
  if (!name) return
  const token = localStorage.getItem('pantau_token')
  const newPath = (currentPath.value.endsWith('/') ? currentPath.value : currentPath.value + '/') + name
  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/mkdir`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ path: newPath })
    })
    const data = await res.json()
    if (data.ok) {
      showNewDirDialog.value = false
      newDirName.value = ''
      notify(`Folder ${name} created`)
      await loadDirectory(currentPath.value, false)
    } else {
      notify(data.detail || 'Failed to create folder', 'error')
    }
  } catch (err) {
    notify('Error creating folder: ' + err.message, 'error')
  }
}

// Rename
function openRenameModal(item) {
  itemToRename.value = item
  renameNewName.value = item.name
}

async function submitRename() {
  if (!itemToRename.value) return
  const newName = renameNewName.value.trim()
  if (!newName || newName === itemToRename.value.name) {
    itemToRename.value = null
    return
  }
  const token = localStorage.getItem('pantau_token')
  const dir = currentPath.value.endsWith('/') ? currentPath.value : currentPath.value + '/'
  const newPath = dir + newName

  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/rename`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        old_path: itemToRename.value.path,
        new_path: newPath
      })
    })
    const data = await res.json()
    if (data.ok) {
      notify(`Renamed to ${newName}`)
      itemToRename.value = null
      await loadDirectory(currentPath.value, false)
    } else {
      notify(data.detail || 'Failed to rename', 'error')
    }
  } catch (err) {
    notify('Error renaming: ' + err.message, 'error')
  }
}

// Chmod
function openChmodModal(item) {
  itemToChmod.value = item
  chmodOctalMode.value = item.is_dir ? '0755' : '0644'
}

async function submitChmod() {
  if (!itemToChmod.value) return
  const mode = chmodOctalMode.value.trim()
  if (!mode) return
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/chmod`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        path: itemToChmod.value.path,
        mode: mode
      })
    })
    const data = await res.json()
    if (data.ok) {
      notify(`Permissions updated to ${mode}`)
      itemToChmod.value = null
      await loadDirectory(currentPath.value, false)
    } else {
      notify(data.detail || 'Failed to update permissions', 'error')
    }
  } catch (err) {
    notify('Error updating permissions: ' + err.message, 'error')
  }
}

// Delete
function confirmDeleteItem(item) {
  itemToDelete.value = item
}

async function executeDeleteItem() {
  if (!itemToDelete.value) return
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/rm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ path: itemToDelete.value.path })
    })
    const data = await res.json()
    if (data.ok) {
      notify(`Deleted: ${itemToDelete.value.name}`)
      itemToDelete.value = null
      await loadDirectory(currentPath.value, false)
    } else {
      notify(data.detail || 'Failed to delete item', 'error')
    }
  } catch (err) {
    notify('Error deleting item: ' + err.message, 'error')
  }
}

// Bulk Delete
async function confirmBulkDelete() {
  if (selectedPaths.value.length === 0) return
  const ok = await confirmAction({
    title: 'Delete Selected Items',
    message: `Are you sure you want to delete ${selectedPaths.value.length} selected items?`,
    confirmText: 'Delete',
    variant: 'danger',
  })
  if (!ok) return

  const token = localStorage.getItem('pantau_token')
  let deletedCount = 0
  for (const path of selectedPaths.value) {
    try {
      const res = await fetch(`/api/servers/${props.server.id}/files/rm`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ path })
      })
      const data = await res.json()
      if (data.ok) deletedCount++
    } catch (err) {
      console.error('Error deleting:', path, err)
    }
  }
  notify(`Deleted ${deletedCount} of ${selectedPaths.value.length} items`)
  selectedPaths.value = []
  await loadDirectory(currentPath.value, false)
}

// Editor
async function openEditor(item) {
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/content?path=${encodeURIComponent(item.path)}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    const data = await res.json()
    if (data.ok) {
      editingFile.value = item
      editorContent.value = data.content
    } else {
      notify(data.detail || 'Unable to open file in editor', 'error')
    }
  } catch (err) {
    notify('Error reading file: ' + err.message, 'error')
  }
}

async function saveEditor() {
  if (!editingFile.value || savingFile.value) return
  savingFile.value = true
  const token = localStorage.getItem('pantau_token')
  try {
    const res = await fetch(`/api/servers/${props.server.id}/files/save`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        path: editingFile.value.path,
        content: editorContent.value,
        make_backup: true
      })
    })
    const data = await res.json()
    if (data.ok) {
      notify(`Saved ${editingFile.value.name}` + (data.backup_created ? ' (.bak created)' : ''))
      await loadDirectory(currentPath.value, false)
    } else {
      notify(data.detail || 'Failed to save file', 'error')
    }
  } catch (err) {
    notify('Error saving file: ' + err.message, 'error')
  } finally {
    savingFile.value = false
  }
}

function closeEditor() {
  editingFile.value = null
}

function downloadFile(item) {
  const token = localStorage.getItem('pantau_token')
  const url = `/api/servers/${props.server.id}/files/download?path=${encodeURIComponent(item.path)}`
  fetch(url, {
    headers: { Authorization: `Bearer ${token}` }
  })
    .then(res => {
      if (!res.ok) throw new Error('File download failed')
      return res.blob()
    })
    .then(blob => {
      const downloadUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = item.name
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(downloadUrl)
      notify(`Downloaded ${item.name}`)
    })
    .catch(err => {
      notify('Download error: ' + err.message, 'error')
    })
}

// Watch props.open to load on open
watch(() => props.open, (newVal) => {
  if (newVal) {
    loadDirectory(currentPath.value)
  }
})
</script>
