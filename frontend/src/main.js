import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { tooltipDirective } from './directives/tooltip'

const app = createApp(App)
app.directive('tooltip', tooltipDirective)
app.mount('#app')
