import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'
const catalog = JSON.parse(readFileSync(new URL('../../../backend/app/profiles/catalog.json', import.meta.url), 'utf8'))

test('Phase 2 options, multiple inputs, semantic correction, trace and refresh', async ({ page }) => {
  let submitted, saved, messages = []
  const datasets = [{ id: 7, original_name: 'sales.csv', status: 'ready', row_count: 2, column_count: 2 }, { id: 8, original_name: 'region.csv', status: 'ready', row_count: 2, column_count: 2 }]
  const plan = { version: '3.0', profiles: [{ name: '数据质量分析' }], depth: 'DEEP', steps: [{ step_id: 'inspect', tool_name: 'dataset_overview', status: 'COMPLETED', input_alias: 'primary' }, { step_id: 'quality', tool_name: 'missing_value_analysis', status: 'COMPLETED', input_alias: 'input_8', depends_on: ['inspect'] }] }
  const result = { record_id: 9, dataset_id: 7, dataset_version_id: 11, status: 'succeeded', answer: '已完成数据质量检查', tool_calls: [], report: { warnings: [], tables: [], charts: [] } }
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    let data = {}
    if (path === '/auth/me') data = { id: 1, username: 'analyst' }
    else if (path === '/workspace/capabilities') data = { file_formats: ['csv'], profile_execution: true, multi_dataset_execution: true, depth_selection: true, depths: ['FAST', 'STANDARD', 'DEEP'], model_selection: true, models: [{ id: 'configured', configured: true }] }
    else if (path === '/analysis/profiles') data = catalog
    else if (path === '/datasets') data = { items: datasets }
    else if (/^\/datasets\/\d+$/.test(path)) data = datasets.find(item => item.id === Number(path.split('/').at(-1)))
    else if (path === '/analysis/sessions') data = { items: [{ id: 5, title: '数据分析' }] }
    else if (path === '/analysis/sessions/5') data = { session: { id: 5, attached_dataset_ids: [7, 8] }, dataset: datasets[0], messages }
    else if (path === '/analysis/sessions/5/semantic-mappings') {
      if (request.method() === 'PATCH') { saved = request.postDataJSON(); data = { version: 2 } }
      else data = { version: saved ? 2 : 1, mappings: [{ column: 'sales', concept: saved?.mappings[0].concept || 'ambiguous_sales', role: 'metric', aggregation: 'none', dataset_version_id: 11, source: saved ? 'user' : 'candidate' }] }
    } else if (path === '/analysis/runs' && request.method() === 'POST') {
      submitted = request.postDataJSON()
      messages = [{ id: 1, role: 'user', content: submitted.question, analysis_record: { id: 9, request_id: submitted.request_id, request_options: submitted } }, { id: 2, role: 'assistant', content: result.answer, status: result.status, analysis_record: { id: 9, status: result.status, dataset_id: 7, dataset_version_id: 11, plan, request_options: submitted } }]
      data = { record_id: 9, status: 'pending' }
    } else if (path === '/analysis/runs/9/trace') data = { plan, steps: [] }
    else if (path === '/analysis/runs/9') data = result
    await route.fulfill({ json: { code: 200, data } })
  })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/analysis/5')
  await page.getByText('确认字段含义', { exact: true }).click()
  await page.getByLabel('sales 的业务含义').fill('quantity')
  await page.getByRole('button', { name: '保存字段含义' }).click()
  await expect(page.getByRole('status').filter({ hasText: '已保存' })).toBeVisible()
  await page.getByLabel('分析深度', { exact: true }).selectOption('DEEP')
  await page.getByLabel('分析模板', { exact: true }).selectOption('general-quality')
  await page.getByRole('checkbox', { name: 'region.csv' }).check()
  await page.getByLabel('分析问题').fill('检查两个表的数据质量')
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect.poll(() => submitted?.depth).toBe('DEEP')
  expect(submitted.profile_ids).toEqual(['general-quality'])
  expect(submitted.inputs.map(item => item.dataset_id)).toEqual([7, 8])
  await expect(page.getByText('已完成数据质量检查', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('分析深度', { exact: true })).toHaveValue('DEEP')
  await expect(page.getByRole('checkbox', { name: 'region.csv' })).toBeChecked()
  await page.getByText('确认字段含义', { exact: true }).click()
  await expect(page.getByLabel('sales 的业务含义')).toHaveValue('quantity')
  await page.screenshot({ path: '../.superpowers/sdd/phase2/workspace-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(() => page.locator('#workspace-navigation').evaluate(element => element.getBoundingClientRect().right)).toBeLessThanOrEqual(0)
  await page.getByRole('complementary', { name: '工件与分析证据' }).getByRole('button', { name: '关闭工件面板', exact: true }).click()
  await page.getByLabel('分析深度', { exact: true }).selectOption('STANDARD')
  await expect(page.getByLabel('分析深度', { exact: true })).toHaveValue('STANDARD')
  await page.getByLabel('sales 的业务含义').scrollIntoViewIfNeeded()
  await expect(page.getByRole('button', { name: '保存字段含义' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: '../.superpowers/sdd/phase2/workspace-mobile.png', fullPage: true, animations: 'disabled' })
  expect(saved.mappings[0].dataset_version_id).toBe(11)
  expect(errors).toEqual([])
})
