// One checked sample feeds every visual direction. This file does not request data.
const sample = Object.freeze({
  file: 'sales_demo.csv',
  rows: 10,
  regions: Object.freeze([
    { name: '华南', orders: 3, sales: 12439 },
    { name: '华东', orders: 3, sales: 10777 },
    { name: '西南', orders: 2, sales: 9979 },
    { name: '华北', orders: 2, sales: 3898 },
  ]),
})

const formatNumber = new Intl.NumberFormat('zh-CN')
const total = sample.regions.reduce((sum, region) => sum + region.sales, 0)
const maximum = Math.max(...sample.regions.map((region) => region.sales))

if (total !== 37093 || sample.regions.reduce((sum, region) => sum + region.orders, 0) !== sample.rows) {
  throw new Error('销售样例的展示值不一致')
}

const chartMarkup = `<div class="chart-bars" role="list" aria-label="各地区销售额，单位元">${sample.regions.map((region) => `
  <div class="chart-row" role="listitem">
    <span>${region.name}</span>
    <div class="chart-track" aria-hidden="true"><span class="chart-fill" style="--width:${(region.sales / maximum * 100).toFixed(1)}%"></span></div>
    <span class="chart-value">${formatNumber.format(region.sales)}</span>
  </div>`).join('')}</div>`

const tableMarkup = `<div class="result-table-wrap"><table class="result-table">
  <caption class="visually-hidden">sales_demo.csv 按地区汇总的订单数与销售额</caption>
  <thead><tr><th scope="col">地区</th><th scope="col">订单数</th><th scope="col">销售额 / 元</th></tr></thead>
  <tbody>${sample.regions.map((region) => `<tr><td>${region.name}</td><td>${region.orders}</td><td>${formatNumber.format(region.sales)}</td></tr>`).join('')}</tbody>
  <tfoot><tr><th scope="row">合计</th><td>${sample.rows}</td><td>${formatNumber.format(total)}</td></tr></tfoot>
</table></div>`

document.querySelectorAll('[data-chart]').forEach((target) => { target.innerHTML = chartMarkup })
document.querySelectorAll('[data-table]').forEach((target) => { target.innerHTML = tableMarkup })

const variants = ['A', 'B', 'C', 'D', 'E']
const titles = {
  A: '清晰对话', B: 'Agent 执行舱', C: '可信指标台', D: '数据工坊', E: '分析审阅台',
}

function showVariant(key, updateHistory = false) {
  const chosen = variants.includes(key) ? key : 'A'
  document.querySelectorAll('.view').forEach((view) => { view.hidden = view.dataset.variant !== chosen })
  document.querySelectorAll('[data-select]').forEach((link) => {
    if (link.dataset.select === chosen) link.setAttribute('aria-current', 'page')
    else link.removeAttribute('aria-current')
  })
  document.title = `${titles[chosen]} · DataLens Agent 五种开源项目启发 UI`
  if (updateHistory) {
    const url = new URL(window.location.href)
    url.searchParams.set('variant', chosen)
    try { window.history.pushState(null, '', url) }
    catch { window.location.href = url.href; return }
    window.scrollTo({ top: 0, behavior: 'instant' })
  }
}

document.querySelectorAll('[data-select]').forEach((link) => {
  link.addEventListener('click', (event) => {
    event.preventDefault()
    showVariant(link.dataset.select, true)
  })
})

window.addEventListener('keydown', (event) => {
  const focused = document.activeElement
  if (event.altKey || event.ctrlKey || event.metaKey || focused?.isContentEditable ||
      ['INPUT', 'TEXTAREA', 'SELECT', 'A', 'BUTTON', 'SUMMARY'].includes(focused?.tagName)) return
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  const current = document.querySelector('[data-select][aria-current="page"]')?.dataset.select || 'A'
  const direction = event.key === 'ArrowLeft' ? -1 : 1
  showVariant(variants[(variants.indexOf(current) + direction + variants.length) % variants.length], true)
})

window.addEventListener('popstate', () => showVariant(new URLSearchParams(window.location.search).get('variant')))
showVariant(new URLSearchParams(window.location.search).get('variant'))
