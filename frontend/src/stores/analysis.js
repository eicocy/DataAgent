import { defineStore } from 'pinia'
import { analysisApi } from '../api/analysis'

const storageKey = 'datalens:analysis'
const terminal = ['succeeded', 'partial', 'failed', 'waiting', 'cancelled']
function minimalPending(value) {
  if (!value || !Number.isInteger(Number(value.session_id)) || (value.dataset_id != null && !Number.isInteger(Number(value.dataset_id))) || typeof value.question !== 'string' || typeof value.request_id !== 'string') return null
  return { session_id: Number(value.session_id), dataset_id: value.dataset_id == null ? null : Number(value.dataset_id), question: value.question, request_id: value.request_id, record_id: value.record_id ?? null }
}
function storedSessions() {
  try {
    const stored = JSON.parse(sessionStorage.getItem(storageKey))
    // 兼容升级前单任务格式，存储中只保留恢复所需的五个字段。
    const values = stored?.session_id ? [stored] : Object.values(stored || {})
    return Object.fromEntries(values.map(minimalPending).filter(Boolean).map((item) => [item.session_id, item]))
  } catch { return {} }
}
export const useAnalysisStore = defineStore('analysis', {
  state: () => ({ pending: null, pendingBySession: {}, result: null, trace: null, error: null }),
  actions: {
    writeStorage() {
      try {
        if (Object.keys(this.pendingBySession).length) sessionStorage.setItem(storageKey, JSON.stringify(this.pendingBySession))
        else sessionStorage.removeItem(storageKey)
      } catch { /* 隐私模式下仍允许分析。 */ }
    },
    persist() {
      if (this.pending) this.pendingBySession[this.pending.session_id] = minimalPending(this.pending)
      this.writeStorage()
    },
    reset() { this.pending = null; this.pendingBySession = {}; this.result = null; this.trace = null; this.error = null; this.writeStorage() },
    restore(sessionId, datasetId, messages = []) {
      this.result = null; this.trace = null
      this.pendingBySession = { ...storedSessions(), ...this.pendingBySession }
      this.pending = this.pendingBySession[Number(sessionId)] || null
      // 服务端运行记录是刷新/其他标签页后的恢复依据，用户消息也携带该记录。
      const active = [...messages].reverse().find((message) => ['pending', 'running'].includes(message.analysis_record?.status))
      if (active) {
        const record = active.analysis_record
        this.pending = minimalPending({ session_id: sessionId, dataset_id: datasetId, question: record.question || active.content, record_id: record.id, request_id: record.request_id })
        if (this.pending) this.persist()
      }
      return this.pending
    },
    async submit(payload, replay = false, config = {}) {
      // 不确定的网络错误复用同一幂等键；明确再次分析才创建新的键。
      this.pendingBySession = { ...storedSessions(), ...this.pendingBySession }
      if (!replay || !this.pending) {
        this.pending = { session_id: payload.session_id, dataset_id: payload.dataset_id, question: payload.question, request_id: crypto.randomUUID(), record_id: null }
        this.result = null; this.trace = null
      }
      const pending = this.pending
      this.persist(); this.error = null
      try {
        const { record_id, ...request } = pending
        const accepted = await analysisApi.submit(request, config)
        if (config.signal?.aborted || this.pending !== pending) return accepted
        pending.record_id = accepted.record_id
        this.result = accepted
        this.persist()
        return accepted
      } catch (error) {
        if (!config.signal?.aborted && this.pending === pending) this.error = error
        throw error
      }
    },
    async poll(signal) {
      const pending = this.pending
      if (!pending?.record_id) return null
      this.error = null
      while (!signal?.aborted && this.pending === pending) {
        const result = await analysisApi.run(pending.record_id, { signal })
        if (signal?.aborted || this.pending !== pending) return null
        this.result = result
        const trace = await analysisApi.trace(pending.record_id, { signal })
        if (signal?.aborted || this.pending !== pending) return null
        this.trace = trace
        if (terminal.includes(result.status)) {
          delete this.pendingBySession[pending.session_id]
          this.pending = null; this.writeStorage()
          return result
        }
        await new Promise((resolve, reject) => {
          const abort = () => { clearTimeout(timer); reject(new DOMException('Polling stopped', 'AbortError')) }
          const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, 1000)
          signal?.addEventListener('abort', abort, { once: true })
        })
      }
      return null
    },
    async watchRun(signal) {
      const pending = this.pending
      if (!pending?.record_id || typeof EventSource === 'undefined') return this.poll(signal)
      return new Promise((resolve, reject) => {
        const stream = new EventSource(`/api/v1/analysis/runs/${pending.record_id}/events`, { withCredentials: true })
        let refreshing = false
        let queued = false
        let finished = false
        const cleanup = () => { stream.close(); signal?.removeEventListener('abort', abort) }
        const abort = () => { if (finished) return; finished = true; cleanup(); reject(new DOMException('Stream stopped', 'AbortError')) }
        const refresh = async () => {
          if (refreshing) { queued = true; return }
          if (finished || signal?.aborted || this.pending !== pending) return
          refreshing = true
          try {
            const result = await analysisApi.run(pending.record_id, { signal })
            if (signal?.aborted || this.pending !== pending) return
            this.result = result
            const trace = await analysisApi.trace(pending.record_id, { signal })
            if (signal?.aborted || this.pending !== pending) return
            this.trace = trace
            if (terminal.includes(result.status)) {
              finished = true; cleanup()
              delete this.pendingBySession[pending.session_id]
              this.pending = null; this.writeStorage()
              resolve(result)
            }
          } catch (error) {
            if (!finished && !signal?.aborted) fallback()
          } finally { refreshing = false; if (queued && !finished) { queued = false; refresh() } }
        }
        const fallback = () => {
          if (finished) return
          finished = true; cleanup()
          this.poll(signal).then(resolve, reject)
        }
        for (const name of ['analysis_queued', 'intent_resolved', 'plan_created', 'plan_updated', 'step_started', 'step_completed', 'step_failed', 'stage_changed', 'response_ready', 'clarification_required', 'analysis_failed', 'analysis_cancelled']) {
          stream.addEventListener(name, refresh)
        }
        stream.onerror = fallback
        signal?.addEventListener('abort', abort, { once: true })
        refresh()
      })
    },
    async cancel() {
      if (!this.pending?.record_id) return null
      return analysisApi.cancel(this.pending.record_id)
    },
  },
})
