import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'

import { analysisApi } from '../src/api/analysis'
import AppShell from '../src/components/AppShell.vue'

vi.mock('../src/api/analysis', () => ({
  analysisApi: { sessions: vi.fn(), updateSession: vi.fn(), removeSession: vi.fn() },
}))

describe('workspace conversation sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    analysisApi.sessions.mockResolvedValue({ items: [
      { id: 2, title: '地区销售', is_pinned: false },
      { id: 1, title: '月度概览', is_pinned: true },
    ] })
    analysisApi.updateSession.mockImplementation(async (id, patch) => ({ id, ...patch }))
    analysisApi.removeSession.mockResolvedValue({})
  })

  function mountShell() {
    return mount(AppShell, {
      global: {
        plugins: [createPinia()],
        mocks: { $route: { params: {}, meta: { title: '智能分析' } }, $router: { push: vi.fn(), replace: vi.fn() } },
        stubs: { RouterLink: { template: '<a><slot /></a>' }, ElIcon: { template: '<span><slot /></span>' },
          ElInput: { props: ["size"], template: '<input />' }, ElButton: { template: '<button><slot /></button>' },
          ElDialog: { props: ['modelValue'], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' } },
      },
    })
  }

  it('loads recent sessions and sends pin and rename updates', async () => {
    const wrapper = mountShell()
    await flushPromises()
    expect(wrapper.text()).toContain('地区销售')
    expect(wrapper.vm.recentSessions.map((item) => item.id)).toEqual([2, 1])

    await wrapper.vm.togglePinned(wrapper.vm.recentSessions[0])
    expect(analysisApi.updateSession).toHaveBeenCalledWith(2, { is_pinned: true })
    expect(wrapper.vm.recentSessions[0].is_pinned).toBe(true)

    wrapper.vm.startRename(wrapper.vm.recentSessions[0])
    wrapper.vm.editingTitle = '新的标题'
    await wrapper.vm.saveRename(wrapper.vm.recentSessions[0])
    expect(analysisApi.updateSession).toHaveBeenLastCalledWith(2, { title: '新的标题' })
    expect(wrapper.vm.recentSessions[0].title).toBe('新的标题')
    wrapper.unmount()
  })

  it('guards duplicate blur and Enter rename submissions', async () => {
    let finish
    analysisApi.updateSession.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = mountShell()
    await flushPromises()
    const session = wrapper.vm.recentSessions[0]
    wrapper.vm.startRename(session)
    wrapper.vm.editingTitle = '一次提交'
    const first = wrapper.vm.saveRename(session)
    await wrapper.vm.saveRename(session)
    expect(analysisApi.updateSession).toHaveBeenCalledTimes(1)
    finish({ id: session.id, title: '一次提交' })
    await first
    wrapper.unmount()
  })

  it('deletes the selected session after explicit confirmation', async () => {
    const wrapper = mountShell()
    await flushPromises()
    wrapper.vm.deleteSessionId = 2
    wrapper.vm.deleteDialogOpen = true
    await wrapper.vm.confirmDeleteSession()
    expect(analysisApi.removeSession).toHaveBeenCalledWith(2)
    expect(wrapper.vm.deleteDialogOpen).toBe(false)
    expect(analysisApi.sessions).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
