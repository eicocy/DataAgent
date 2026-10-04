import { test, expect } from '@playwright/test'
const schema = { columns: [{ name: 'id' }, { name: 'amount' }] }
const quality = { kind: 'quality_score', rule_version: 'quality-score-v1', status: 'valid', score: 90, row_count: 3, findings: [{ issue: 'duplicate_rows', count: 1, severity: 'warning', suggestion: '核对重复行', row_refs: [2] }], configured_rules: {}, key_candidates: [], explanation: '公开描述性规则' }
const frame = { row_count: 3, column_count: 2, schema, sample: [{ id: '1', amount: '9007199254740993.12' }], quality }
const metrics = { mae: 1, rmse: 2, mape: null, mape_coverage: 0, mape_explanation: '零目标不参与 MAPE' }
const forecast = { kind: 'forecast', history_start: '2024-01-01', history_end: '2024-12-01', observation_count: 12, selected_model: 'naive', aggregation: 'sum', granularity: 'month', horizon: 1, baseline: { metrics }, metrics, folds: [], candidates: [], points: [{ time: '2025-01-01', value: 12, lower: 9, upper: 15 }], uncertainty: { residual_count: 3, limitations: '残差样本有限' }, limitations: ['不保证未来误差范围'], source_ref: 'forecast_step' }

test('Phase 3 document confirmation, quality, cleaning and join save, forecast display', async ({ page }) => {
 let version = 11, versionNumber = 1, confirmed, cleanSubmit, joinSubmit, run
 const source = { id: 4, name: '原文.docx', type: 'docx', status: 'ready', size: 300, dataset_ids: [], candidates: [{ id: 'table-1', location: { table_index: 0 }, row_count: 4 }] }
 const dataset = () => ({ id: 7, original_name: '提取数据.csv', status: 'ready', current_version_id: version, row_count: 3, column_count: 2, file_type: 'csv' })
 const versions = () => Array.from({ length: versionNumber }, (_, index) => ({ id: 11 + index, dataset_id: 7, version_number: index + 1, schema, status: 'ready' }))
 const errors = []; page.on('pageerror', error => errors.push(error.message))
 await page.route('**/api/v1/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname.replace('/api/v1', '')
  let data = {}
  if (path === '/auth/me') data = { id: 1, username: 'analyst' }
  else if (path === '/files') data = { items: [source], total: 1, page: 1, page_size: 20 }
  else if (path === '/files/4') data = { ...source, preview: '文档原文：id amount' }
  else if (path === '/files/4/extractions/table-1') data = { rows: [['id','amount'],['1','10']], columns: ['column_1','column_2'], total: 4 }
  else if (path === '/files/4/extractions/table-1/datasets') { confirmed = request.postDataJSON(); data = { dataset: dataset(), file: source } }
  else if (path === '/artifacts') data = { items: [], has_more: false }
  else if (path === '/datasets') data = { items: [dataset(), { id: 8, original_name: '右表.csv', status: 'ready' }], total: 2 }
  else if (path === '/datasets/7') data = dataset()
  else if (path === '/datasets/7/versions') data = versions()
  else if (path === '/datasets/8/versions') data = [{ id: 21, version_number: 1, schema }]
  else if (path === '/datasets/7/columns') data = schema.columns.map(item => ({ ...item, sample_values: [] }))
  else if (path === '/datasets/7/preview') data = { rows: frame.sample, columns: ['id','amount'], total_rows: 3 }
  else if (path === '/datasets/7/quality') data = quality
  else if (path.endsWith('/transformations/preview')) data = { dataset_version_id: version, preview_hash: 'a'.repeat(64), before: frame, after: { ...frame, row_count: 2 }, result: { kind: 'cleaning_plan', steps: [{ operation: 'remove_duplicates', row_count: 2, changed_cells: 0, added_missing: 0 }] } }
  else if (path === '/datasets/7/transformations') { cleanSubmit = request.postDataJSON(); data = { execution_id: 31, status: 'pending' } }
  else if (path === '/datasets/7/transformations/31') { version = 12; versionNumber = 2; data = { status: 'succeeded', output_version: versions().at(-1) } }
  else if (path.endsWith('/joins/preview')) data = { dataset_version_id: version, preview_hash: 'b'.repeat(64), before: frame, after: frame, result: { kind: 'join', row_count: 3, left_key_cardinality: 3, right_key_cardinality: 3, unmatched_left_rows: 0, unmatched_right_rows: 0, source_versions: { left: version, right: 21 } } }
  else if (path === '/datasets/7/joins') { joinSubmit = request.postDataJSON(); data = { execution_id: 32, status: 'pending' } }
  else if (path === '/datasets/7/joins/32') { version = 13; versionNumber = 3; data = { status: 'succeeded', output_version: versions().at(-1) } }
  else if (path === '/workspace/capabilities') data = { file_formats: ['csv','jsonl','docx','pdf','txt'], profile_execution: true }
  else if (path === '/analysis/profiles') data = { items: [], categories: [] }
  else if (path === '/analysis/sessions/5/semantic-mappings') data = { mappings: [] }
  else if (path === '/analysis/sessions/5') data = { session: { id: 5, attached_dataset_ids: [7] }, dataset: dataset(), messages: [] }
  else if (path === '/analysis/sessions') data = { items: [] }
  else if (path === '/analysis/runs') { run = request.postDataJSON(); data = { record_id: 9, status: 'pending' } }
  else if (path === '/analysis/runs/9/trace') data = { plan: null, steps: [] }
  else if (path === '/analysis/runs/9') data = { record_id: 9, status: 'succeeded', answer: '预测已完成', tool_result: forecast, tool_calls: [{ step_id: 'forecast_step', tool_name: 'forecast_data', status: 'succeeded', result_summary: '预测完成' }], report: { tables: [{ kind: 'forecast', columns: ['time','value','lower','upper'], rows: forecast.points, row_count: 1, truncated: false, source_ref: 'forecast_step', limitations: forecast.limitations }], charts: [], warnings: [] } }
  await route.fulfill({ json: { code: 200, data } })
 })
 await page.goto('/files')
 await page.getByRole('button', { name: '原文.docx · docx · 就绪' }).click()
 await expect(page.getByRole('button', { name: '确认并创建数据集' })).toBeDisabled()
 await page.getByText('我已核对原文位置、表头和样例数据').check()
 await page.getByRole('button', { name: '确认并创建数据集' }).click()
 await expect.poll(() => confirmed?.confirmed).toBe(true)
 expect(confirmed.request_id).toBeTruthy()
 await page.goto('/datasets/7')
 await page.getByRole('tab', { name: '数据质量' }).click()
 await expect(page.getByText('核对重复行')).toBeVisible()
 await page.getByRole('tab', { name: '清洗', exact: true }).click()
 await expect(page.getByRole('button', { name: '保存为新版本', exact: true })).toBeDisabled()
 await page.getByRole('button', { name: '添加清洗步骤' }).click()
 await page.getByLabel('步骤 1 清洗操作').selectOption('remove_duplicates')
 await page.getByLabel('步骤 1 目标字段').selectOption(['id'])
 await page.getByLabel('重复记录保留').selectOption('first')
 await page.getByRole('button', { name: '预览清洗' }).click()
 await expect(page.getByRole('heading', { name: '版本 11 的变更预览' })).toBeVisible()
 await page.getByRole('button', { name: '保存为新版本', exact: true }).click()
 await page.getByRole('dialog').getByRole('button', { name: '保存为新版本', exact: true }).click()
 await expect.poll(() => cleanSubmit?.dataset_version_id).toBe(11)
 await expect(page.getByText('已保存新版本 2')).toBeVisible()
 await page.getByLabel('查看数据版本').selectOption('12')
 await page.getByRole('tab', { name: '合并', exact: true }).click()
 await page.getByLabel('右表', { exact: true }).selectOption('8')
 await page.getByLabel('右表固定版本').selectOption('21')
 await page.getByLabel('键对 1 左表字段').selectOption('id')
 await page.getByLabel('键对 1 右表字段').selectOption('id')
 await page.getByLabel('合并方式').selectOption('left')
 await page.getByLabel('声明键关系').selectOption('many_to_one')
 await page.getByRole('button', { name: '预览合并' }).click()
 await expect(page.getByText('来源版本：左 12 · 右 21')).toBeVisible()
 await page.getByRole('button', { name: '保存为新版本', exact: true }).click()
 await page.getByRole('dialog').getByRole('button', { name: '保存为新版本', exact: true }).click()
 await expect(page.getByText('已保存新版本 3')).toBeVisible()
 expect(joinSubmit.right_version_id).toBe(21); expect(joinSubmit.confirmed).toBe(true)
 await page.goto('/analysis/5')
 await page.getByLabel('分析问题').fill('预测下个月金额')
 await page.getByRole('button', { name: '发送问题' }).click()
 await expect(page.getByText('经验误差范围，未经校准。它不保证未来真实值落入范围。')).toBeVisible()
 expect(run.session_id).toBe(5)
 await page.screenshot({ path: '../.superpowers/sdd/phase3-v203/task6-desktop.png', fullPage: true })
 await page.setViewportSize({ width: 390, height: 844 })
 await expect.poll(() => page.locator('#workspace-navigation').evaluate(element => element.getBoundingClientRect().right)).toBeLessThanOrEqual(0)
 await page.emulateMedia({ reducedMotion: 'reduce' })
 await page.getByLabel('分析问题').focus()
 await expect(page.getByLabel('分析问题')).toBeFocused()
 await page.screenshot({ path: '../.superpowers/sdd/phase3-v203/task6-mobile.png', fullPage: true })
 expect(errors).toEqual([])
})

test('Phase 3 owned document list failure retry, no-table honest state and narrow keyboard controls', async ({ page }) => {
 let attempts = 0
 await page.route('**/api/v1/**', async route => {
  const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
  if (path === '/files' && ++attempts === 1) { await route.fulfill({ status: 503, json: { code: 'TEMPORARY', message: '文件列表暂不可用' } }); return }
  const data = path === '/auth/me' ? { id: 1, username: 'analyst' } : path === '/files' ? { items: [{ id: 4, name: '说明.txt', type: 'txt', status: 'ready', dataset_ids: [] }], total: 1 } : path === '/files/4' ? { id: 4, name: '说明.txt', status: 'ready', preview: '这是没有表格的说明文档', candidates: [] } : { items: [], has_more: false }
  await route.fulfill({ json: { code: 200, data } })
 })
 await page.goto('/files')
 await expect(page.getByRole('alert')).toContainText('文件列表暂不可用')
 await page.getByRole('alert').getByRole('button', { name: '重试', exact: true }).click()
 const fileButton = page.getByRole('button', { name: '说明.txt · txt · 就绪' })
 await fileButton.focus(); await page.keyboard.press('Enter')
 await expect(page.getByText('未识别到表格。文档已作为附件保存；可在文件页面查看，暂不能作为数值分析输入。')).toBeVisible()
 await expect(page.getByRole('button', { name: '确认并创建数据集' })).toHaveCount(0)
 await page.getByText('查看提取原文').click()
 await expect(page.getByText('这是没有表格的说明文档')).toBeVisible()
 await page.setViewportSize({ width: 390, height: 844 })
 await expect.poll(() => page.locator('#workspace-navigation').evaluate(element => element.getBoundingClientRect().right)).toBeLessThanOrEqual(0)
 await page.getByRole('button', { name: '收起附件预览' }).focus()
 await page.keyboard.press('Enter')
 await expect(page.getByText('未识别到表格。文档已作为附件保存；可在文件页面查看，暂不能作为数值分析输入。')).toHaveCount(0)
 await page.screenshot({ path: '../.superpowers/sdd/phase3-v203/task6-document-mobile.png', fullPage: true })
})

test('Phase 3 normalized-only forecast table stays honest about unavailable validation details', async ({ page }) => {
 await page.route('**/api/v1/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
  let data = { items: [], total: 0 }
  if (path === '/auth/me') data = { id: 1, username: 'analyst' }
  else if (path === '/analysis/sessions/5') data = { session: { id: 5, attached_dataset_ids: [] }, dataset: null, messages: [] }
  else if (path === '/workspace/capabilities') data = { file_formats: ['csv'] }
  else if (path === '/analysis/profiles') data = { items: [], categories: [] }
  else if (path === '/analysis/runs') data = { record_id: 9, status: 'pending' }
  else if (path === '/analysis/runs/9/trace') data = { plan: null, steps: [] }
  else if (path === '/analysis/runs/9') data = { record_id: 9, status: 'succeeded', answer: '结果表已保存', tool_calls: [{ step_id: 'forecast_step', status: 'succeeded', tool_name: 'forecast_data', result_summary: '预测点已计算' }], report: { charts: [], warnings: [], tables: [{ kind: 'forecast', columns: ['time','value','lower','upper'], rows: forecast.points, row_count: 1, truncated: false, source_ref: 'forecast_step', limitations: ['仅保留预测点表，未提供验证详情'] }] } }
  await route.fulfill({ json: { code: 200, data } })
 })
 await page.goto('/analysis/5')
 await page.getByLabel('分析问题').fill('查看已保存的预测结果')
 await page.getByRole('button', { name: '发送问题' }).click()
 await expect(page.getByText('当前仅提供结果表，完整计算信息未提供，无法展示完整指标或验证详情。')).toBeVisible()
 await expect(page.getByRole('cell', { name: '2025-01-01', exact: true })).toBeVisible()
 await expect(page.getByRole('region', { name: '预测结果', exact: true })).toHaveCount(0)
 await expect(page.getByRole('columnheader', { name: 'MAE', exact: true })).toHaveCount(0)
 await expect(page.getByText('仅保留预测点表，未提供验证详情')).toBeVisible()
})
