import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import PromptComposer from '../src/components/PromptComposer.vue'
import UploadQueue from '../src/components/UploadQueue.vue'
import { datasetApi } from '../src/api/datasets'

vi.mock('../src/api/datasets', () => ({ datasetApi: { upload: vi.fn(), detail: vi.fn(), inspectSheets: vi.fn() } }))

describe('workspace composer and upload queue', () => {
  beforeEach(() => vi.clearAllMocks())
  it('preserves IME composition and permits deliberate Enter submission', async () => {
    const wrapper = mount(PromptComposer, { props: { modelValue: '分析销售' } })
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', isComposing: true })
    expect(wrapper.emitted('submit')).toBeUndefined()
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', isComposing: false })
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.get('input[type=file]').attributes('multiple')).toBeDefined()
    wrapper.unmount()
  })
  it('uploads sequentially, retains failed items and retries only the failed file', async () => {
    datasetApi.upload.mockRejectedValueOnce(new Error('解析服务暂不可用')).mockResolvedValue({ id: 7 })
    datasetApi.detail.mockResolvedValue({ id: 7, status: 'ready', original_name: 'good.csv' })
    const wrapper = mount(UploadQueue, { global: { plugins: [createPinia()] } })
    await wrapper.vm.addFiles([new File(['a\n1'], 'bad.csv'), new File(['a\n2'], 'good.csv')])
    await flushPromises()
    expect(wrapper.vm.items.map(item => item.status)).toEqual(['failed', 'ready'])
    expect(wrapper.text()).toContain('解析服务暂不可用')
    await wrapper.vm.retry(wrapper.vm.items[0])
    await flushPromises()
    expect(datasetApi.upload).toHaveBeenCalledTimes(3)
    expect(wrapper.emitted('ready')).toHaveLength(2)
    wrapper.unmount()
  })
  it('validates oversized and unsupported files without uploading them', async () => {
    const wrapper = mount(UploadQueue, { global: { plugins: [createPinia()] } })
    await wrapper.vm.addFiles([new File(['text'], 'scan.pdf')])
    expect(datasetApi.upload).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂不支持')
    wrapper.unmount()
  })
  it('resumes an accepted dataset after transient polling failure without posting again', async () => {
    datasetApi.upload.mockResolvedValue({ id: 7 })
    datasetApi.detail.mockRejectedValueOnce(new Error('网络暂不可用')).mockResolvedValue({ id: 7, status: 'ready' })
    const wrapper = mount(UploadQueue, { global: { plugins: [createPinia()] } })
    await wrapper.vm.addFiles([new File(['a\n1'], 'sales.csv')])
    expect(wrapper.vm.items[0].status).toBe('failed')
    await wrapper.vm.retry(wrapper.vm.items[0])
    expect(datasetApi.upload).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.items[0].status).toBe('ready')
    wrapper.unmount()
  })
  it('counts restored attachments toward the server attachment limit', async () => {
    const wrapper = mount(UploadQueue, { props: { attachedIds: Array.from({ length: 10 }, (_, i) => i + 1) }, global: { plugins: [createPinia()] } })
    await wrapper.vm.addFiles([new File(['a\n1'], 'extra.csv')])
    expect(datasetApi.upload).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('最多保留 10 个文件')
    wrapper.unmount()
  })
})
