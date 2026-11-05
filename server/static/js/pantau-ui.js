/**
 * Pantau Server - Universal Client UI Library (pantau-ui.js)
 * Standar pustaka antarmuka pengguna untuk pembuatan komponen dinamis, modal, dan ikon kanonikal.
 */

(function(window) {
  'use strict';

  const SVG_ICONS = {
    eye: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
    edit: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path></svg>`,
    trash: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`,
    history: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>`,
    play: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`,
    pause: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>`,
    close: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
    check: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
    alert: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
    refresh: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>`
  };

  const PantauUI = {
    icons: SVG_ICONS,

    serverDetailBtn: function(serverId, title) {
      const isEn = (typeof isCurrentLangEn === 'function') ? isCurrentLangEn() : false;
      const t = title || (isEn ? 'Server Details' : 'Buka Rincian Server');
      return `<a href="/servers/${serverId}" class="pantau-btn-icon" title="${t}" aria-label="${t}">${this.icons.eye}</a>`;
    },

    serverEditBtn: function(serverId, title) {
      const isEn = (typeof isCurrentLangEn === 'function') ? isCurrentLangEn() : false;
      const t = title || (isEn ? 'Edit Configuration' : 'Edit Konfigurasi Server');
      return `<a href="/servers/${serverId}/edit" class="pantau-btn-icon" title="${t}" aria-label="${t}">${this.icons.edit}</a>`;
    },

    actionBtn: function(iconKey, options) {
      const opt = options || {};
      const icon = this.icons[iconKey] || '';
      const title = opt.title || '';
      const variantCls = opt.variant ? `pantau-btn-icon-${opt.variant}` : '';
      if (opt.href) {
        return `<a href="${opt.href}" class="pantau-btn-icon ${variantCls}" title="${title}" aria-label="${title}" ${opt.attr || ''}>${icon}</a>`;
      }
      return `<button type="${opt.type || 'button'}" class="pantau-btn-icon ${variantCls}" title="${title}" aria-label="${title}" ${opt.attr || ''}>${icon}</button>`;
    },

    badge: function(text, variant) {
      const v = variant || 'muted';
      return `<span class="badge badge-${v}">${text}</span>`;
    },

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
