import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'
import path from 'node:path'

const root=path.resolve(import.meta.dirname,'..')
const database=path.join(root,'artifacts',`browser-${Date.now()}.db`).replaceAll('\\','/')
const python=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python')
const channel=process.env.PLAYWRIGHT_CHANNEL || (process.platform==='win32'&&existsSync('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')?'msedge':undefined)
const hostedUrl=process.env.NATURAX_E2E_BASE_URL
const reportPrefix=hostedUrl?'vercel-':''

export default defineConfig({
  testDir:'./e2e', timeout:hostedUrl?240000:90000, workers:1, fullyParallel:false,
  expect:{timeout:hostedUrl?90000:5000},
  reporter:[['list'],['json',{outputFile:`../artifacts/${reportPrefix}browser-results.json`}],['html',{outputFolder:`../artifacts/${reportPrefix}browser-report`,open:'never'}]],
  outputDir:`../artifacts/${reportPrefix}browser-test-output`,
  use:{baseURL:hostedUrl||'http://127.0.0.1:8011',channel,headless:true,viewport:{width:1440,height:1000},screenshot:'only-on-failure',trace:'retain-on-failure',actionTimeout:hostedUrl?60000:15000},
  webServer:hostedUrl?undefined:{command:`"${python}" -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8011`,url:'http://127.0.0.1:8011/api/health',timeout:30000,reuseExistingServer:false,env:{NATURAX_DATABASE_URL:`sqlite:///${database}`}},
})
