import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AnalysisResult from '../src/components/AnalysisResult.vue'
import fixture from './fixtures/phase3-parallel-result.json'

// Saved API DTO from simulated sales data; these tests never invoke a model.
const render = evidence => mount(AnalysisResult, { props: { evidence }, global: { stubs: { ChartView: true, ElButton: true } } })
const copy = () => structuredClone(fixture)

describe('parallel result provenance', () => {
  it('retains forecast, contribution and period despite period completing last', () => {
    const wrapper = render(copy())
    expect(wrapper.findAll('[aria-label="预测结果"]')).toHaveLength(1)
    expect(wrapper.findAll('[aria-label="业务指标结果"]')).toHaveLength(2)
    expect(wrapper.vm.typedEntries.map(entry => entry.source.artifact_id)).toEqual([6, 7, 8])
    expect(wrapper.text()).toContain('2300.20000000')
    expect(wrapper.text()).toContain('2026-07-01')
    expect(wrapper.text()).toContain('3.594354477737491')
  })
  it('matches a unique verified full payload without a plan', () => {
    const evidence = copy(); delete evidence.plan
    expect(render(evidence).vm.typedEntries.map(entry => entry.source.artifact_id)).toEqual([6, 7, 8])
  })
  it('preserves ambiguous equal payloads from distinct sources without a plan', () => {
    const evidence = copy(); delete evidence.plan
    evidence.report.tables.push({ ...structuredClone(evidence.report.tables[1]), source_ref: 'other_forecast', artifact_id: 99 })
    const wrapper = render(evidence)
    expect(wrapper.findAll('[aria-label="预测结果"]')).toHaveLength(3)
    expect(wrapper.findAll('[aria-label="业务指标结果"]')).toHaveLength(2)
  })
  it('preserves another forecast with a different dataset and historical range', () => {
    const evidence = copy()
    evidence.report.tables.push({ ...structuredClone(evidence.report.tables[1]), source_ref: 'other_forecast', artifact_id: 99, dataset_id: 22, history_start: '2023-10-01T00:00:00' })
    const wrapper = render(evidence)
    expect(wrapper.findAll('[aria-label="预测结果"]')).toHaveLength(2)
    expect(wrapper.findAll('[aria-label="业务指标结果"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('2023-10-01')
  })
  it('uses the completed plan artifact to resolve identical payloads from two real sources', () => {
    const evidence = copy()
    evidence.report.tables.push({ ...structuredClone(evidence.report.tables[1]), source_ref: 'other_forecast', artifact_id: 99 })
    const wrapper = render(evidence)
    expect(wrapper.vm.typedEntries.map(entry => entry.source.artifact_id)).toEqual([6, 7, 8, 99])
    expect(wrapper.findAll('[aria-label="预测结果"]')).toHaveLength(2)
  })
  it('honors explicit raw artifact identity even when a different forecast has identical values', () => {
    const evidence = copy()
    evidence.tool_result.artifact_id = 99
    evidence.report.tables.push({ ...structuredClone(evidence.report.tables[1]), source_ref: 'other_forecast', artifact_id: 99 })
    expect(render(evidence).vm.typedEntries.map(entry => entry.source.artifact_id)).toEqual([99, 6, 7, 8])
  })
})
