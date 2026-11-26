import { ref, computed } from 'vue'
import en from './en.js'
import id from './id.js'

const translations = {
  en,
  id,
}

// Strict English-only interface policy (for now)
export const currentLocale = ref('en')

export function setLocale(locale) {
  currentLocale.value = 'en'
}

export function toggleLocale() {
  currentLocale.value = 'en'
}

export function t(key, params = {}) {
  const dict = translations.en
  let text = dict[key] || key
  for (const [k, v] of Object.entries(params)) {
    text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), v)
  }
  return text
}

// Composition API helper
export function useI18n() {
  return {
    locale: currentLocale,
    setLocale,
    toggleLocale,
    t,
  }
}
