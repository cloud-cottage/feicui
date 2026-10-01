import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { startBackendWatch } from './composables/useBackendStatus'
import './styles/base.css'

// 全局后端连通性探测（dev-only 端点；见 vite.config.js / README §3）
startBackendWatch(5000)

createApp(App).use(router).mount('#app')
