/**
 * Pantau Server - Universal Client UI & Component Blueprint Engine (pantau-ui.js)
 * Standar cetak biru tunggal untuk rendering komponen dinamis antarmuka web Pantau Server.
 * Menghilangkan hardcoded inline styles dan perenderan string sporadis di seluruh template.
 */

(function(window) {
  'use strict';

  // 1. REGISTRI IKON VEKTOR BAKU (SVG ICONS BLUEPRINT)
  const SVG_ICONS = {
    eye: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
    edit: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>`,
    trash: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`,
    history: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>`,
    play: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`,
    pause: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>`,
    stop: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="5" width="14" height="14" rx="2"></rect></svg>`,
    restart: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`,
    reload: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path></svg>`,
    power: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line></svg>`,
    log: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>`,
    terminal: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>`,
    pulse: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>`,
    shield: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
    check: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
    close: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
    alert: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
    refresh: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`,
    sortNeutral: `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" class="sort-icon-svg" style="opacity:0.35"><polyline points="7 15 12 20 17 15"></polyline><polyline points="7 9 12 4 17 9"></polyline></svg>`,
    sortAsc: `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" class="sort-icon-svg" style="color:var(--blue);opacity:1"><polyline points="7 9 12 4 17 9"></polyline></svg>`,
    sortDesc: `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" class="sort-icon-svg" style="color:var(--blue);opacity:1"><polyline points="7 15 12 20 17 15"></polyline></svg>`
  };

  // Helper escape HTML
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // 2. MESIN KOMPONEN PUSAT (PANTAU UI BLUEPRINT)
  const PantauUI = {
    icons: SVG_ICONS,
    escape: escapeHtml,

    /**
     * Komponen Badge Baku
     * @param {string} text - Teks badge
     * @param {string} variant - 'danger' | 'warn' | 'orange' | 'info' | 'up' | 'muted'
     * @param {object} options - { dot: boolean, title: string, extraCls: string, mono: boolean }
     */
    badge: function(text, variant, options) {
      const opt = options || {};
      const v = variant || 'muted';
      const dotHtml = opt.dot ? `<span class="dot ${v === 'up' ? 'up' : 'down'}" style="margin-right:4px"></span>` : '';
      const monoCls = opt.mono ? 'mono' : '';
      const titleAttr = opt.title ? `title="${escapeHtml(opt.title)}"` : '';
      const extraCls = opt.extraCls || '';
      return `<span class="badge badge-${v} ${monoCls} ${extraCls}" ${titleAttr}>${dotHtml}${escapeHtml(text)}</span>`;
    },

    /**
     * Tombol Aksi Baku (24x24px NOC Standard)
     * @param {string} iconKey - Kunci ikon di SVG_ICONS
     * @param {object} options - { title, onClick, href, variant: 'primary'|'danger'|'ghost', extraCls, attr }
     */
    btnAct: function(iconKey, options) {
      const opt = options || {};
      const iconSvg = this.icons[iconKey] || '';
      const title = opt.title ? escapeHtml(opt.title) : '';
      const titleAttr = title ? `title="${title}" aria-label="${title}"` : '';
      const variantCls = opt.variant ? `btn-act-${opt.variant}` : '';
      const extraCls = opt.extraCls || '';
      const attr = opt.attr || '';

      if (opt.href) {
        return `<a href="${opt.href}" class="btn-act ${variantCls} ${extraCls}" ${titleAttr} ${attr}>${iconSvg}</a>`;
      }
      const clickAttr = opt.onClick ? `onclick="${opt.onClick}"` : '';
      return `<button type="${opt.type || 'button'}" class="btn-act ${variantCls} ${extraCls}" ${titleAttr} ${clickAttr} ${attr}>${iconSvg}</button>`;
    },

    /**
     * Wadah Kapsul Tombol Aksi Baku (Action Button Group)
     * @param {Array<string>} buttonsHtmlArray
     */
    actionGroup: function(buttonsHtmlArray) {
      if (!Array.isArray(buttonsHtmlArray) || buttonsHtmlArray.length === 0) return '—';
      return `<div class="action-btn-group">${buttonsHtmlArray.filter(Boolean).join('')}</div>`;
    },

    /**
     * Meter Progres Baku (CPU, RAM, Storage NOC Progress Bar)
     * @param {number} percent
     * @param {object} options - { type: 'cpu'|'ram'|'storage', label: string }
     */
    progressBar: function(percent, options) {
      const opt = options || {};
      const p = Math.min(100, Math.max(0, Number(percent) || 0));
      let colorVar = 'var(--green)';
      if (p >= 90) colorVar = 'var(--red)';
      else if (p >= 75) colorVar = 'var(--yellow)';

      const label = opt.label || `${p.toFixed(1)}%`;
      return `
        <div class="pantau-progress-wrap" title="${escapeHtml(label)}">
          <div class="pantau-progress-bar" style="width:${p}%;background:${colorVar}"></div>
        </div>
      `;
    },

    /**
     * Sel Tabel Baku (Rata Kiri Terkunci)
     * @param {string} content - Konten HTML di dalam sel
     * @param {object} options - { cls, title, mono: boolean, sortVal, colSpan }
     */
    td: function(content, options) {
      const opt = options || {};
      const clsList = [];
      if (opt.cls) clsList.push(opt.cls);
      if (opt.mono) clsList.push('mono');
      const clsAttr = clsList.length ? `class="${clsList.join(' ')}"` : '';
      const titleAttr = opt.title ? `title="${escapeHtml(opt.title)}"` : '';
      const sortAttr = opt.sortVal !== undefined ? `data-sort-val="${escapeHtml(String(opt.sortVal))}"` : '';
      const colSpanAttr = opt.colSpan ? `colspan="${opt.colSpan}"` : '';
      return `<td ${clsAttr} ${titleAttr} ${sortAttr} ${colSpanAttr}>${content}</td>`;
    },

    /**
     * Baris Tabel Baku
     * @param {Array<string>} cellsArray - Array string <td>...</td>
     * @param {object} options - { id, cls, dataAttrs, style }
     */
    tr: function(cellsArray, options) {
      const opt = options || {};
      const idAttr = opt.id ? `id="${opt.id}"` : '';
      const clsAttr = opt.cls ? `class="${opt.cls}"` : '';
      const dataAttr = opt.dataAttrs || '';
      const styleAttr = opt.style ? `style="${opt.style}"` : '';
      return `<tr ${idAttr} ${clsAttr} ${dataAttr} ${styleAttr}>${cellsArray.join('')}</tr>`;
    },

    /**
     * Baris Tabel Kosong Baku (Universal Empty Row)
     * @param {number} colSpan
     * @param {string} message
     */
    emptyRow: function(colSpan, message) {
      const cs = colSpan || 7;
      const msg = message || 'Tidak ada data yang cocok dengan kriteria filter.';
      return `
        <tr class="pantau-empty-tr">
          <td colspan="${cs}" class="pantau-empty-td empty-msg">
            <div class="pantau-empty-box">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.35;margin-bottom:6px">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="8" y1="12" x2="16" y2="12"></line>
              </svg>
              <span>${escapeHtml(msg)}</span>
            </div>
          </td>
        </tr>
      `;
    },

    /**
     * Header Kolom Terurut (Sortable Column Header)
     * @param {string} title - Judul kolom
     * @param {string} colKey - Kunci pengurutan
     * @param {string} currentState - 'asc' | 'desc' | 'none'
     * @param {object} options - { width, cls, onClick }
     */
    th: function(title, colKey, currentState, options) {
      const opt = options || {};
      let icon = this.icons.sortNeutral;
      if (currentState === 'asc') icon = this.icons.sortAsc;
      else if (currentState === 'desc') icon = this.icons.sortDesc;

      const clickAttr = opt.onClick ? `onclick="${opt.onClick}"` : '';
      const widthStyle = opt.width ? `style="width:${opt.width}"` : '';
      const cls = opt.cls ? `class="${opt.cls}"` : '';

      return `
        <th ${cls} ${widthStyle} ${clickAttr} data-sort-key="${colKey}">
          <div style="display:inline-flex;align-items:center;gap:4px">
            <span>${escapeHtml(title)}</span>
            <span>${icon}</span>
          </div>
        </th>
      `;
    },

    /**
     * Manajemen Dialog / Modal Universal
     */
    modal: function(id) {
      const el = document.getElementById(id);
      return {
        open: function() {
          if (el) el.style.display = 'flex';
        },
        close: function() {
          if (el) el.style.display = 'none';
        }
      };
    }
  };

  window.PantauUI = PantauUI;
})(window);
