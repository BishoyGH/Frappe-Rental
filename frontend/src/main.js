import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './index.css'

// All server calls go through frappe-ui's request helper (CSRF token from the boot data).
setConfig('resourceFetcher', frappeRequest)

createApp(App).use(router).use(FrappeUI).mount('#app')
