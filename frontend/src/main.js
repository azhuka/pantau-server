import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { initTooltipEngine } from './utils/tooltip'

const app = createApp(App)
app.mount('#app')
initTooltipEngine()
