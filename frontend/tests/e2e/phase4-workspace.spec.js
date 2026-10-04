import { test, expect } from '@playwright/test'

test('Phase 4 restores selection, reads full-result pages and sends structured references', async ({ page }) => {
 let selected = 41, submitted
 const dataset = { id: 7, original_name: '模拟数据.csv', status: 'ready', current_version_id: 11, row_count: 150, column_count: 1 }
 const versions = [{ alias: 'primary', dataset_id: 7, dataset_version_id: 11 }]
 const artifact = { id: 41, artifact_id: 41, session_id: 5, name: '完整结果', type: 'table', status: 'READY', dataset_versions: versions, download_url: '/api/v1/artifacts/41/download', source_artifact_ids: [], expires_at: null }
 const errors = []; page.on('pageerror', error => errors.push(error.message))
 await page.route('**/api/v1/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname.replace('/api/v1','')
  let data = {}
  if (path === '/auth/me') data = { id: 1, username: 'analyst' }
  else if (path === '/datasets') data = { items: [dataset], total: 1 }
  else if (path === '/datasets/7') data = dataset
  else if (path === '/datasets/7/versions') data = [{ id: 11, version_number: 1, schema: { columns: [{ name: 'amount' }] } }]
  else if (path === '/workspace/capabilities') data = { profile_execution: true, artifact_references: true, automatic_reports: true, report_templates: ['auto','quick','detailed','executive','technical','data_quality','forecast'].map(id => ({ id, name: id })) }
  else if (path === '/analysis/profiles') data = { items: [], categories: [] }
  else if (path === '/analysis/sessions') data = { items: [] }
  else if (path === '/analysis/sessions/5') data = { session: { id: 5, attached_dataset_ids: [7] }, dataset, messages: [] }
  else if (path === '/analysis/sessions/5/semantic-mappings') data = { mappings: [] }
  else if (path === '/analysis/sessions/5/workspace') {
   if (req.method() === 'PATCH') selected = req.postDataJSON().selected_artifact_id
   data = { artifacts: { items: [artifact], has_more: false }, selected_artifact_id: selected, reports: [], latest_analysis: null }
  }
  else if (path === '/artifacts/41/preview') {
   const offset = Number(new URL(req.url()).searchParams.get('offset') || 0)
   data = { preview: { kind: 'table', offset, total: 150, columns: ['amount'], rows: Array.from({ length: Math.min(100,150-offset) }, (_,i) => ({ amount: i+offset })) } }
  }
  else if (path === '/analysis/runs' && req.method() === 'POST') { submitted = req.postDataJSON(); data = { record_id: 9, status: 'pending' } }
  else if (path === '/analysis/runs/9/trace') data = { steps: [], plan: null }
  else if (path === '/analysis/runs/9') data = { record_id: 9, status: 'succeeded', answer: '引用分析完成', report: { tables: [], charts: [], warnings: [] }, tool_calls: [] }
  await route.fulfill({ json: { code: 200, data } })
 })
 await page.goto('/analysis/5')
 await expect(page.getByRole('heading', { name: '会话成果' })).toBeVisible()
 await expect(page.getByText('150 行 · 当前预览 100 行')).toBeVisible()
 await page.getByRole('button', { name: '下一页明细' }).click()
 await expect(page.getByText('150 行 · 当前预览 50 行')).toBeVisible()
 await page.getByRole('button', { name: '@ 引用', exact: true }).click()
 await page.getByLabel('分析问题').fill('基于已有结果生成详细报告')
 await page.getByLabel('报告类型').selectOption('detailed')
 await page.getByRole('button', { name: '发送问题' }).click()
 await expect.poll(() => submitted?.artifact_refs).toEqual([41])
 expect(submitted.report_template).toBe('detailed')
 expect(submitted.inputs[0].dataset_version_id).toBe(11)
 await page.reload()
 await expect(page.getByText('150 行 · 当前预览 100 行')).toBeVisible()
 await page.screenshot({ path: '../.superpowers/sdd/phase4/workspace-desktop.png', fullPage: true })
 await page.emulateMedia({ reducedMotion: 'reduce' })
 await page.setViewportSize({ width: 390, height: 844 })
 await expect.poll(() => page.locator('#workspace-navigation').evaluate(element => element.getBoundingClientRect().right)).toBeLessThanOrEqual(0)
 await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
 await page.screenshot({ path: '../.superpowers/sdd/phase4/workspace-mobile.png', fullPage: true })
 expect(errors).toEqual([])
})
