import { readFileSync } from 'node:fs'
import { test, expect } from '@playwright/test'

const catalog = JSON.parse(readFileSync(new URL('../../../backend/app/profiles/catalog.json', import.meta.url), 'utf8'))

test('landing, template, multi-file failure/retry, attachments refresh and narrow screen', async ({ page }) => {
  let sessionCount = 0, failedOnce = false, attachments = []
  const datasets = []
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    let data = {}
    if (path === '/auth/me') data = { id: 1, username: 'analyst' }
    else if (path === '/workspace/capabilities') data = { file_formats: ['csv', 'xlsx'], models: [{ id: 'configured-model' }], max_files: 10 }
    else if (path === '/analysis/profiles') data = catalog
    else if (path === '/datasets/upload') {
      const bad = request.postDataBuffer().includes(Buffer.from('bad.csv'))
      if (bad && !failedOnce) { failedOnce = true; return route.fulfill({ status: 503, json: { code: 'UPLOAD_UNAVAILABLE', message: '上传服务暂不可用' } }) }
      data = { id: 7 + datasets.length, original_name: bad ? 'bad.csv' : 'good.csv', status: 'ready', row_count: 2, column_count: 2 }
      datasets.push(data)
    } else if (/^\/datasets\/\d+$/.test(path)) data = datasets.find(item => item.id === Number(path.split('/').at(-1)))
    else if (path === '/datasets') data = { items: datasets, total: datasets.length }
    else if (path === '/analysis/sessions' && request.method() === 'POST') { sessionCount++; data = { id: 5 } }
    else if (path === '/analysis/sessions') data = { items: sessionCount ? [{ id: 5, title: '新分析' }] : [] }
    else if (path === '/analysis/sessions/5' && request.method() === 'PATCH') { attachments = request.postDataJSON().attached_dataset_ids; data = { id: 5, attached_dataset_ids: attachments } }
    else if (path === '/analysis/sessions/5') data = { session: { id: 5, attached_dataset_ids: attachments }, dataset: null, messages: [] }
    await route.fulfill({ json: { code: 200, data } })
  })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Hey！今天想分析什么数据？' })).toBeVisible()
  expect(sessionCount).toBe(0)
  await page.screenshot({ path: '../.superpowers/sdd/upgrade-plan/landing-desktop.png', fullPage: true, animations: 'disabled' })
  await page.getByLabel('分析方向', { exact: true }).selectOption('general')
  await page.getByLabel('分析模板', { exact: true }).selectOption('general-quality')
  await expect(page.getByLabel('分析问题')).toHaveValue('看看这个表有什么数据问题。')
  await expect(page.getByLabel('分析深度')).toBeDisabled()
  await page.getByLabel('选择数据文件', { exact: true }).setInputFiles([
    { name: 'bad.csv', mimeType: 'text/csv', buffer: Buffer.from('region,sales\nEast,2') },
    { name: 'good.csv', mimeType: 'text/csv', buffer: Buffer.from('region,sales\nWest,3') },
  ])
  await expect(page.getByText('上传服务暂不可用')).toBeVisible()
  await expect(page.getByText('已就绪', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByText('已就绪', { exact: true })).toHaveCount(2)
  await expect.poll(() => attachments).toEqual([7, 8])
  expect(sessionCount).toBe(1)
  await expect(page.getByLabel('分析问题')).toHaveValue('看看这个表有什么数据问题。')
  await page.reload()
  await expect(page.getByRole('button', { name: 'good.csv', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'bad.csv', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '移除附件 good.csv', exact: true }).click()
  await expect.poll(() => attachments).toEqual([8])
  await expect(page.getByRole('button', { name: 'good.csv', exact: true })).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByLabel('分析问题')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await expect.poll(() => page.locator('.sidebar').evaluate(el => el.getBoundingClientRect().right)).toBeLessThanOrEqual(0)
  await page.screenshot({ path: '../.superpowers/sdd/upgrade-plan/landing-mobile.png', fullPage: true, animations: 'disabled' })
  await page.getByRole('button', { name: '打开导航' }).click()
  await page.getByRole('link', { name: '分析模板', exact: true }).click()
  await expect(page.getByRole('heading', { name: '数据质量分析' })).toBeVisible()
  await page.getByRole('button', { name: '预测分析', exact: true }).click()
  await expect(page.getByRole('button', { name: '规划中', exact: true }).first()).toBeDisabled()
  await page.screenshot({ path: '../.superpowers/sdd/upgrade-plan/templates-mobile.png', fullPage: true })
  expect(errors).toEqual([])
})
