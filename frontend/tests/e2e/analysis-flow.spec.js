import { test, expect } from '@playwright/test'

// 浏览器交互契约测试使用受控 API，真实 MySQL/模型验收另行执行。
test('signup, upload, preview, queued analysis and history with mocked APIs', async ({ page }) => {
  let authenticated = false
  let polls = 0
  const dataset = { id: 7, original_name: 'sales.csv', status: 'ready', row_count: 2, column_count: 2, file_type: 'csv', quality_warnings: ['演示数据缺失一个值'] }
  const result = { record_id: 9, session_id: 5, status: 'succeeded', answer: '总销售额为 12。', tool_calls: [{ tool_name: 'aggregate_data', status: 'succeeded', result_summary: '返回真实汇总' }], tool_result: { columns: ['sales_sum'], rows: [{ sales_sum: 12 }] } }
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    let data = {}
    if (path === '/auth/me' && !authenticated) return route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED', message: '请登录' } })
    if (path === '/auth/register') { authenticated = true; data = { id: 1, username: 'demo_user' } }
    else if (path === '/auth/me') data = { id: 1, username: 'demo_user' }
    else if (path === '/datasets/upload' || path === '/datasets/7') data = dataset
    else if (path === '/datasets/7/columns') data = [{ name: 'sales', original_name: 'sales', data_type: 'integer', sample_values: [5, 7] }]
    else if (path === '/datasets/7/preview') data = { rows: [{ sales: 5 }, { sales: 7 }], columns: ['sales'], total_rows: 2 }
    else if (path === '/analysis/sessions' && route.request().method() === 'POST') data = { id: 5 }
    else if (path === '/analysis/sessions/5') data = { dataset, messages: [] }
    else if (path === '/analysis/runs' && route.request().method() === 'POST') data = { record_id: 9, session_id: 5, status: 'pending' }
    else if (path === '/analysis/runs/9') data = ++polls < 3 ? { record_id: 9, status: 'running' } : result
    else if (path === '/analysis/runs/9/trace') data = { steps: result.tool_calls }
    else if (path === '/history/9') data = { ...result, id: 9, question: '总销售额', dataset, final_answer: result.answer }
    else if (path === '/datasets') data = { items: [dataset], total: 1 }
    await route.fulfill({ json: { code: 'OK', data } })
  })
  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill('demo_user')
  await page.getByLabel('密码', { exact: true }).fill('password123')
  await page.getByLabel('确认密码').fill('password123')
  await page.getByRole('button', { name: '创建账号' }).click()
  await page.waitForURL('/')
  await page.goto('/datasets/upload')
  await page.locator('input[type=file]').setInputFiles({ name: 'sales.csv', mimeType: 'text/csv', buffer: Buffer.from('region,sales\nEast,5\nWest,7') })
  await page.getByRole('button', { name: /上传并解析/ }).click()
  await page.waitForURL('**/datasets/7')
  await expect(page.getByText('演示数据缺失一个值')).toBeVisible()
  await page.getByRole('button', { name: '开始分析' }).click()
  await page.waitForURL('**/analysis?*')
  await page.getByLabel('分析问题').fill('总销售额')
  await page.getByRole('button', { name: '发送问题' }).click()
  await expect(page.getByRole('button', { name: '取消任务' })).toBeVisible()
  await page.reload()
  await expect(page.getByText('总销售额为 12。')).toBeVisible()
  await expect(page.getByText('aggregate_data', { exact: true })).toBeVisible()
  await page.goto('/history/9')
  await expect(page.getByText('总销售额为 12。')).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: '再次分析' })).toBeVisible()
})
