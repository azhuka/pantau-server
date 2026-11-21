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
            title="Open Web Terminal at this path"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="4 17 10 11 4 5"/>
              <line x1="12" y1="19" x2="20" y2="19"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Quick Bookmarks Bar (matching ~/rj45) -->
      <div class="bg-[#04060d] border-b border-cyan-500/15 px-3 py-1 flex items-center gap-1.5 flex-wrap text-[11px] select-none">
        <span class="text-[10px] uppercase font-bold text-gray-400 flex items-center gap-1 tracking-wider mr-1">
          <svg class="w-3 h-3 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
          </svg>
          Bookmarks:
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
            <span>New File</span>
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
            <span>New Folder</span>
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

      <!-- Feedback Notification Toast -->
      <div
        v-if="feedbackMsg"
        class="mx-3 mt-2 px-3 py-1.5 rounded text-xs flex items-center justify-between border"
        :class="feedbackMsg.type === 'error' ? 'bg-rose-950/80 border-rose-800 text-rose-300' : 'bg-emerald-950/80 border-emerald-800 text-emerald-300'"
      >
        <span>{{ feedbackMsg.text }}</span>
        <button @click="feedbackMsg = null" class="text-xs ml-2 cursor-pointer">✕</button>
      </div>

      <!-- Directory Items Table -->
      <div class="flex-1 overflow-y-auto p-3 select-text">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="border-b border-cyan-500/20 text-gray-400 uppercase font-bold tracking-wider sticky top-0 bg-[#070b16] select-none z-10">
            <tr>
              <th class="py-2 px-3">File Name</th>
              <th class="py-2 px-3">Permissions</th>
              <th class="py-2 px-3">Owner</th>
              <th class="py-2 px-3">Size</th>
              <th class="py-2 px-3">Modified</th>
              <th class="py-2 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/40">
            <tr
              v-for="item in filteredItems"
              :key="item.path || item.name"
              class="hover:bg-cyan-950/20 transition group"
            >
              <!-- Name & Icon -->
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

              <!-- Permissions -->
              <td class="py-2 px-3 text-gray-400 font-mono text-[11px]">{{ item.perms }}</td>

              <!-- Owner -->
              <td class="py-2 px-3 text-gray-400 font-mono text-[11px]">{{ item.owner }}</td>

              <!-- Size -->
              <td class="py-2 px-3 text-gray-300 font-mono text-[11px]">{{ item.size_human || item.size }}</td>

              <!-- Modified -->
              <td class="py-2 px-3 text-gray-400 font-mono text-[11px]">{{ item.mtime }}</td>

              <!-- Actions -->
              <td class="py-2 px-3 text-right">
                <div class="inline-flex items-center gap-1.5 justify-end">
                  <!-- File: Edit -->
                  <button
                    v-if="!item.is_dir"
                    type="button"
                    @click.stop="openEditor(item)"
                    class="px-2 py-0.5 rounded text-[11px] bg-cyan-950 text-cyan-300 border border-cyan-800 hover:bg-cyan-900 cursor-pointer font-bold inline-flex items-center gap-1 transition"
                    title="Edit File"
                  >
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                    </svg>
                    <span>Edit</span>
                  </button>

                  <!-- File: Download -->
                  <button
                    v-if="!item.is_dir"
                    type="button"
                    @click.stop="downloadFile(item)"
                    class="w-6 h-6 flex items-center justify-center rounded text-[11px] bg-gray-900 text-gray-300 border border-gray-700 hover:bg-gray-800 hover:text-cyan-300 cursor-pointer transition"
                    title="Download File"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/>
                      <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                  </button>

                  <!-- Directory: Open -->
                  <button
                    v-if="item.is_dir && item.name !== '.. (parent)'"
                    type="button"
                    @click.stop="loadDirectory(item.path)"
                    class="w-6 h-6 flex items-center justify-center rounded text-[11px] bg-cyan-950/80 text-cyan-300 border border-cyan-800 hover:bg-cyan-900 cursor-pointer transition"
                    title="Open Directory"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="9 18 15 12 9 6"/>
                    </svg>
                  </button>

                  <!-- Delete File/Directory -->
                  <button
                    v-if="item.name !== '.. (parent)'"
                    type="button"
                    @click.stop="confirmDeleteItem(item)"
                    class="w-6 h-6 flex items-center justify-center rounded text-[11px] bg-gray-900 text-rose-400 border border-gray-800 hover:bg-rose-950 hover:border-rose-700 cursor-pointer transition"
                    :title="item.is_dir ? 'Delete Directory' : 'Delete File'"
                  >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                  </button>
                </div>
              </td>
            </tr>

            <!-- Empty / No Items row -->
            <tr v-if="filteredItems.length === 0 && !loading">
              <td colspan="6" class="py-8 text-center text-gray-500 italic">
                {{ searchFilter ? 'No matching files found' : 'Empty directory' }}
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
              Cancel
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
import { ref, computed, watch, nextTick } from 'vue'

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

// Address bar manual input
const isManualPathInput = ref(false)
const manualPathInputValue = ref('')
const manualPathInputRef = ref(null)

// Actions state
const showNewFileDialog = ref(false)
const newFileName = ref('')
const showNewDirDialog = ref(false)
const newDirName = ref('')
const itemToDelete = ref(null)
const feedbackMsg = ref(null)

// Editor state
const editingFile = ref(null)
const editorContent = ref('')
const savingFile = ref(false)

// Quick bookmarks matching ~/rj45
const bookmarks = [
  { label: '~ Home', path: '/root', title: 'Operator Home (/root)' },
  { label: '/ Root', path: '/', title: 'Root Filesystem (/)' },
  { label: '/var/log', path: '/var/log', title: 'System Logs (/var/log)' },
  { label: '/etc', path: '/etc', title: 'System Config (/etc)' },
  { label: '/opt', path: '/opt', title: 'Optional Software (/opt)' },
  { label: '/var/www', path: '/var/www', title: 'Web Data (/var/www)' }
]

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
  if (!searchFilter.value) return items.value
  const q = searchFilter.value.toLowerCase()
  return items.value.filter(i => i.name.toLowerCase().includes(q))
})

const summaryStats = computed(() => {
  const dirs = items.value.filter(i => i.is_dir && i.name !== '.. (parent)').length
  const files = items.value.filter(i => !i.is_dir).length
  return `${items.value.length} items (${dirs} folders, ${files} files)`
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
  } else if (showNewFileDialog.value) {
    showNewFileDialog.value = false
  } else if (showNewDirDialog.value) {
    showNewDirDialog.value = false
  } else if (itemToDelete.value) {
    itemToDelete.value = null
  } else {
    emit('close')
  }
}

async function loadDirectory(path = currentPath.value, pushToHistory = true) {
  if (!props.server?.id) return
  loading.value = true
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
  emit('open-terminal', {
    ...props.server,
    workingDirectory: currentPath.value
  })
}

function popoutWindow() {
  window.open(
    `/?standalone=files&sid=${props.server.id}`,
    `pantau_fm_${props.server.id}`,
    'popup=yes,width=1220,height=820,menubar=no,toolbar=no,status=no'
  )
}

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
