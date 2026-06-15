import type { App } from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import Vant from 'vant'
import 'vant/lib/index.css'

export function registerUiLibraries(app: App<Element>) {
  app.use(Antd)
  app.use(Vant)
}
