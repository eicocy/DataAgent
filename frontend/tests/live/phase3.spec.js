import { test, expect } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const terminal = ['succeeded', 'partial', 'failed', 'waiting', 'cancelled']
const scratch = path.resolve('../.superpowers/sdd/phase3-live')
const csv = 'date,region,product,sales\n2026-01-01,华南,A,10\n2026-01-01,华东,A,20\n2026-02-01,华南,B,30\n2026-02-01,华东,B,40\n'
async function api(request, method, url, data) {
  const headers = method === 'get' ? {} : { Origin: process.env.LIVE_E2E_ORIGIN }
  const response = await request[method]('/api/v1' + url, data === undefined ? { headers } : { data, headers })
  expect(response.ok(), `${method} ${url}: ${response.status()}`).toBeTruthy()
  return (await response.json()).data
}
async function waitRun(request, id) {
  let result
  await expect.poll(async () => {
    result = await api(request, 'get', `/analysis/runs/${id}`)
    return terminal.includes(result.status)
  }, { timeout: 190000, intervals: [200, 500, 1000] }).toBeTruthy()
  fs.writeFileSync(path.join(scratch, `run-${id}.json`), JSON.stringify(result, null, 2))
  return result
}
async function submit(page, question, reload = false) {
  await page.getByLabel('分析问题').fill(question)
  const accepted = page.waitForResponse(r => r.url().endsWith('/api/v1/analysis/runs') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '发送问题' }).click()
  const response = await accepted
  expect(response.ok(), `analysis submission: ${response.status()}`).toBeTruthy()
  const { data } = await response.json()
  if (reload) await page.reload()
  const result = await waitRun(page.request, data.record_id)
  await expect(page.getByRole('button', { name: '取消任务' })).toBeHidden({ timeout: 10000 })
  return result
}
function numericValues(result) {
  return (result.tool_result?.rows || []).flatMap(row => Object.values(row).filter(v => typeof v === 'number'))
}
function control(action, id) {
  return JSON.parse(execFileSync(path.resolve('../backend/.venv/Scripts/python.exe'),
    [path.resolve('../backend/tests/live_control.py'), action, String(id)], { cwd: path.resolve('..'), encoding: 'utf8' }))
}

test('real MySQL and DeepSeek: upload, clarification, pinned follow-ups, evidence and recovery', async ({ page, browser }) => {
  fs.mkdirSync(scratch, { recursive: true })
  const username = 'p3_live_' + Date.now().toString(16)
  const password = randomUUID() + 'P3'
  await page.goto('/register')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByLabel('确认密码').fill(password)
  await page.getByRole('button', { name: '创建账号' }).click()
  await page.waitForURL(url => url.pathname === '/')
  const datasets = []
  for (const [name, source] of [['phase3_sales.csv', csv], ['phase3_other.csv', csv.replace(/,10\n/, ',100\n')]]) {
    await page.goto('/datasets/upload')
    await page.locator('input[type=file]').setInputFiles({ name, mimeType: 'text/csv', buffer: Buffer.from(source) })
    await page.getByRole('button', { name: /上传并解析/ }).click()
    await page.waitForURL(/\/datasets\/\d+$/, { timeout: 30000 })
    await expect(page.getByRole('button', { name: '开始分析' })).toBeVisible({ timeout: 30000 })
    datasets.push(Number(new URL(page.url()).pathname.split('/').at(-1)))
  }
  await page.goto('/analysis')
  await page.waitForURL(/\/analysis\/\d+/)
  const chat = await submit(page, '你好')
  expect(chat.status).toBe('succeeded')
  expect(chat.tool_calls).toHaveLength(0)
  expect((await api(page.request, 'get', `/analysis/runs/${chat.record_id}/trace`)).plan).toBeNull()
  const question = '按地区（region）汇总销售额（sales）的总和，展示各地区金额，并绘制饼图。'
  const ambiguous = await submit(page, question)
  expect(ambiguous.status).toBe('waiting')
  expect([...ambiguous.agent_response.clarification.candidate_dataset_ids].sort((a, b) => a - b))
    .toEqual([...datasets].sort((a, b) => a - b))
  await page.reload()
  await expect(page.getByRole('button', { name: '选择 phase3_sales.csv', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '选择 phase3_sales.csv', exact: true }).click()
  const aggregate = await submit(page, question, true)
  expect(aggregate.status).toBe('succeeded')
  expect(numericValues(aggregate).sort((a, b) => a - b)).toEqual([40, 60])
  expect(aggregate.evidence.length).toBeGreaterThan(0)
  const originalVersion = aggregate.dataset_version_id
  const originalTrace = await api(page.request, 'get', `/analysis/runs/${aggregate.record_id}/trace`)
  fs.writeFileSync(path.join(scratch, 'first-plan.json'), JSON.stringify(originalTrace, null, 2))
  const modelMetadata = control('metadata', aggregate.record_id)
  expect(modelMetadata.calls.every(c => c.provider === 'deepseek' && c.model && c.latency_ms >= 0)).toBeTruthy()
  expect(modelMetadata.calls.some(c => c.input_tokens > 0 && c.output_tokens > 0)).toBeTruthy()
  expect(modelMetadata.calls.map(c => c.prompt_version)).toEqual(expect.arrayContaining([
    'intent_router.v2', 'analysis_planner.v3', 'result_interpreter.v3']))
  expect(modelMetadata.stored_fields.some(name => /raw|prompt_text|prompt_json/.test(name))).toBeFalsy()

  // Abort only the SSE connection. All polling and analysis calls use real APIs.
  await page.route('**/analysis/runs/*/events', route => route.abort())
  const south = await submit(page, '只看华南')
  await page.unroute('**/analysis/runs/*/events')
  expect(south.status).toBe('succeeded')
  expect(south.dataset_version_id).toBe(originalVersion)
  expect(numericValues(south)).toContain(40)
  expect(numericValues(south)).not.toContain(60)
  const bar = await submit(page, '换成柱状图')
  expect(bar.status).toBe('succeeded')
  expect(bar.dataset_version_id).toBe(originalVersion)
  expect(bar.chart.type).toBe('bar')
  expect(bar.tool_calls.filter(c => !c.reused).map(c => c.tool_name)).toEqual(['generate_chart'])
  const trace = await api(page.request, 'get', `/analysis/runs/${bar.record_id}/trace`)
  const source = trace.plan.steps.find(s => s.tool_name !== 'generate_chart' && s.result_ref)
  expect(source).toBeTruthy()
  expect((await api(page.request, 'get', `/analysis/runs/${bar.record_id}/results/${source.result_ref.split(':')[1]}`)).rows.length).toBeGreaterThan(0)

  const stream = await page.request.get(`/api/v1/analysis/runs/${bar.record_id}/events`)
  expect(stream.ok()).toBeTruthy()
  const ids = [...(await stream.text()).matchAll(/^id: (\d+)$/gm)].map(m => Number(m[1]))
  expect(ids.length).toBeGreaterThan(1)
  const cursor = ids[Math.floor(ids.length / 2)]
  const replay = await page.request.get(`/api/v1/analysis/runs/${bar.record_id}/events`, { headers: { 'Last-Event-ID': String(cursor) } })
  expect([...(await replay.text()).matchAll(/^id: (\d+)$/gm)].map(m => Number(m[1]))).toEqual(ids.filter(id => id > cursor))

  control('expire', bar.record_id)
  const recomputed = await submit(page, '换成柱状图')
  expect(recomputed.status).toBe('succeeded')
  expect(numericValues(recomputed)).toContain(40)
  expect(recomputed.dataset_version_id).toBe(originalVersion)
  expect(recomputed.tool_calls.some(c => !c.reused && c.tool_name !== 'generate_chart')).toBeTruthy()
  control('version-unavailable', recomputed.record_id)
  try {
    const unavailable = await submit(page, '换成柱状图')
    expect(unavailable.status).toBe('waiting')
    expect(unavailable.tool_calls).toHaveLength(0)
  } finally { control('version-restore', recomputed.record_id) }

  const switched = await submit(page, '使用第二个文件，按region汇总sales总和，不继承之前的地区过滤条件。')
  expect(switched.status).toBe('succeeded')
  expect(switched.dataset_id).toBe(datasets[1])
  expect(numericValues(switched).sort((a, b) => a - b)).toEqual([60, 130])
  expect(control('context', switched.record_id).filters).toEqual([])

  const foreignContext = await browser.newContext({ baseURL: process.env.LIVE_E2E_ORIGIN })
  try {
    await api(foreignContext.request, 'post', '/auth/register', { username: 'p3_live_other_' + Date.now().toString(16), password: randomUUID() })
    for (const suffix of ['', '/trace', '/events', `/results/${source.result_ref.split(':')[1]}`]) {
      expect((await foreignContext.request.get(`/api/v1/analysis/runs/${bar.record_id}${suffix}`)).status()).toBe(404)
    }
    expect((await foreignContext.request.post(`/api/v1/analysis/runs/${bar.record_id}/cancel`,
      { headers: { Origin: process.env.LIVE_E2E_ORIGIN } })).status()).toBe(404)
  } finally { await foreignContext.close() }

  const queued = await api(page.request, 'post', '/analysis/runs', { session_id: switched.session_id, dataset_id: switched.dataset_id, question: '按region汇总sales', request_id: randomUUID() })
  expect(queued.status).toBe('pending')
  await api(page.request, 'post', `/analysis/runs/${queued.record_id}/cancel`, {})
  expect((await waitRun(page.request, queued.record_id)).status).toBe('cancelled')
  const running = await api(page.request, 'post', '/analysis/runs', { session_id: switched.session_id, dataset_id: switched.dataset_id, question: '按region汇总sales总和，按product汇总sales总和，分别绘制柱状图，最后详细解释结果。', request_id: randomUUID() })
  await expect.poll(async () => {
    const value = await api(page.request, 'get', `/analysis/runs/${running.record_id}/trace`)
    return value.plan?.steps.some(s => s.status === 'COMPLETED') || false
  }, { timeout: 60000, intervals: [100, 200] }).toBeTruthy()
  const before = await api(page.request, 'get', `/analysis/runs/${running.record_id}`)
  expect(before.status).toBe('running')
  await api(page.request, 'post', `/analysis/runs/${running.record_id}/cancel`, {})
  const cancelled = await waitRun(page.request, running.record_id)
  expect(cancelled.status).toBe('cancelled')
  const cancelledTrace = await api(page.request, 'get', `/analysis/runs/${running.record_id}/trace`)
  expect(cancelledTrace.plan.steps.some(s => s.status === 'COMPLETED')).toBeTruthy()
  expect(cancelledTrace.plan.steps.every(s => ['COMPLETED', 'FAILED', 'CANCELLED'].includes(s.status))).toBeTruthy()
  for (const step of cancelledTrace.plan.steps.filter(s => s.status === 'COMPLETED' && s.result_ref)) {
    expect((await page.request.get(`/api/v1/analysis/runs/${running.record_id}/results/${step.result_ref.split(':')[1]}`)).ok()).toBeTruthy()
  }
  await page.reload()
  await expect(page.getByLabel('分析问题')).toBeVisible()
  await page.screenshot({ path: path.join(scratch, 'browser-phase3.png'), fullPage: true })
  fs.writeFileSync(path.join(scratch, 'browser-evidence.json'), JSON.stringify({ username, api_mock: false,
    datasets, model_metadata: modelMetadata.calls, runs: { chat: chat.record_id, aggregate: aggregate.record_id, south: south.record_id,
      chart: bar.record_id, expired: recomputed.record_id, switched: switched.record_id, cancelled: running.record_id },
    checks: ['upload','dataset_free_chat','ambiguity','numeric_binding','pinned_filter','chart_reuse',
      'model_metadata','sse_fallback','sse_replay','expiry_recompute','version_unavailable','dataset_switch','isolation','queued_cancel','running_cancel'] }, null, 2))
})
