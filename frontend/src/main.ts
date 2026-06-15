import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './app/router'
import { createPinia } from 'pinia'
import { registerUiLibraries } from './app/providers/ui'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
registerUiLibraries(app)
app.mount('#app')
