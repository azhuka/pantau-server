<template>
  <div>
    <div class="topbar">
      <h2>Kustomisasi Tampilan &amp; Tema UI</h2>
    </div>

    <div class="card" style="max-width:700px">
      <div class="card-header">
        <h3>Tema Warna &amp; Palet Antarmuka</h3>
      </div>

      <div style="display:flex;flex-direction:column;gap:18px">
        <div>
          <div class="filter-label" style="margin-bottom:8px">Pilih Tema</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:10px">
            <button v-for="t in themes" :key="t.id"
                    :class="['btn', currentTheme === t.id ? 'btn-primary' : 'btn-ghost']"
                    @click="setTheme(t.id)">
              {{ t.name }}
            </button>
          </div>
        </div>

        <div>
          <div class="filter-label" style="margin-bottom:8px">Kepadatan Data (Density)</div>
          <div style="display:flex;gap:10px">
            <button v-for="d in densities" :key="d.id"
                    :class="['btn', currentDensity === d.id ? 'btn-primary' : 'btn-ghost']"
                    @click="setDensity(d.id)">
              {{ d.name }}
            </button>
          </div>
        </div>

        <div>
          <div class="filter-label" style="margin-bottom:8px">Font Tipografi Monospace</div>
          <div style="display:flex;gap:10px">
            <button v-for="f in fonts" :key="f.id"
                    :class="['btn', currentFont === f.id ? 'btn-primary' : 'btn-ghost']"
                    @click="setFont(f.id)">
              {{ f.name }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const themes = [
  { id: 'dark', name: 'Midnight NOC' },
  { id: 'obsidian', name: 'Obsidian OLED' },
  { id: 'navy', name: 'Navy Slate' },
  { id: 'light', name: 'Light Modern' },
];

const densities = [
  { id: 'compact', name: 'Kompak (NOC Baku)' },
  { id: 'normal', name: 'Normal' },
];

const fonts = [
  { id: 'system', name: 'Monospace Sistem' },
  { id: 'jetbrains', name: 'JetBrains Mono' },
  { id: 'fira', name: 'Fira Code' },
];

const currentTheme = ref(localStorage.getItem('pantau_theme') || 'dark');
const currentDensity = ref(localStorage.getItem('pantau_density') || 'compact');
const currentFont = ref(localStorage.getItem('pantau_font_mono') || 'system');

function setTheme(t) {
  currentTheme.value = t;
  localStorage.setItem('pantau_theme', t);
  document.documentElement.setAttribute('data-theme', t);
}

function setDensity(d) {
  currentDensity.value = d;
  localStorage.setItem('pantau_density', d);
  document.documentElement.setAttribute('data-density', d);
}

function setFont(f) {
  currentFont.value = f;
  localStorage.setItem('pantau_font_mono', f);
  document.documentElement.setAttribute('data-font-mono', f);
}
</script>
