import { ref, computed } from 'vue'
import en from './en.js'
import id from './id.js'

const savedLocale = 'en'
export const currentLocale = ref('en')

const translations = {
  en,
  id,
}

export function setLocale(locale) {
  currentLocale.value = 'en'
}

export function toggleLocale() {
  currentLocale.value = 'en'
}

export function t(key, params = {}) {
  const dict = translations[currentLocale.value] || translations.en
  let text = dict[key] || translations.en[key] || key
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
