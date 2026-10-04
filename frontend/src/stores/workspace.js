import { defineStore } from 'pinia'
import { workspaceApi } from '../api/workspace'
import { reportsApi } from '../api/reports'
// Keep writes ordered per store without putting Promises in persisted state.
const selectionWrites = new WeakMap()

export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({ sessionId: null, items: [], reports: [], selectedId: null, preview: null,
    latestAnalysis: null, loading: false, previewLoading: false, error: '', offset: 0,
    hasMore: false, generation: 0, selectionToken: 0, selectedArtifact: null }),
  getters: { selected: state => state.items.find(item => (item.id || item.artifact_id) === state.selectedId) || (state.selectedArtifact?.id === state.selectedId ? state.selectedArtifact : null) },
  actions: {
    reset() { this.generation++; this.selectionToken++; this.sessionId = null; this.items = []; this.reports = []; this.preview = null; this.selectedId = null; this.selectedArtifact = null; this.latestAnalysis = null; this.error = ''; this.loading = false; this.previewLoading = false; this.offset = 0; this.hasMore = false },
    async load(id, config = {}, append = false) {
      if (!id) { this.reset(); return }
      if (this.sessionId !== id) { this.reset(); this.sessionId = id }
      const generation = ++this.generation
      this.loading = true; this.error = ''
      try {
        const value = await workspaceApi.restore(id, { offset: append ? this.offset + 50 : 0, limit: 50 }, config)
        if (generation !== this.generation || config.signal?.aborted) return
        this.items = append ? [...this.items, ...(value.artifacts?.items || [])] : value.artifacts?.items || []
        this.offset = value.artifacts?.offset || 0; this.hasMore = Boolean(value.artifacts?.has_more)
        this.reports = value.reports || []; this.latestAnalysis = value.latest_analysis || null
        const selected = append ? this.selectedId : value.selected_artifact_id
        this.selectedId = selected || null
        if (!append) this.selectedArtifact = value.selected_artifact || null
        if (selected) await this.select(selected, config, false)
        else this.preview = null
      } catch (error) { if (generation === this.generation && !config.signal?.aborted) this.error = error.message || '成果恢复失败，可重试' }
      finally { if (generation === this.generation) this.loading = false }
    },
    async select(id, config = {}, persist = true, offset = 0) {
      const generation = this.generation, token = ++this.selectionToken, sessionId = this.sessionId
      this.selectedId = id; this.preview = null; this.previewLoading = true; this.error = ''
      try {
        if (persist) {
          const write = (selectionWrites.get(this) || Promise.resolve()).catch(() => {}).then(() => {
            if (generation !== this.generation || config.signal?.aborted) return
            return workspaceApi.select(sessionId, id, config)
          })
          selectionWrites.set(this, write)
          await write
        }
        if (generation !== this.generation || token !== this.selectionToken || config.signal?.aborted) return
        const value = id ? await reportsApi.preview(id, { offset, limit: 100 }, config) : null
        if (generation !== this.generation || token !== this.selectionToken || config.signal?.aborted) return
        this.preview = value?.preview || null
        if (value?.artifact) this.selectedArtifact = value.artifact
      } catch (error) { if (generation === this.generation && token === this.selectionToken && !config.signal?.aborted) this.error = error.message || '成果预览失败，可重试' }
      finally { if (generation === this.generation && token === this.selectionToken) this.previewLoading = false }
    },
  },
})
