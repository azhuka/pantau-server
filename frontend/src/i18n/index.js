import { ref, computed } from 'vue'
import en from './en.js'
import id from './id.js'

const savedLocale = localStorage.getItem('pantau_locale') || 'en'
export const currentLocale = ref(savedLocale)

const translations = {
  en,
  id,
}

export function setLocale(locale) {
  if (translations[locale]) {
    currentLocale.value = locale
    localStorage.setItem('pantau_locale', locale)
  }
}

export function toggleLocale() {
  const next = currentLocale.value === 'en' ? 'id' : 'en'
  setLocale(next)
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
