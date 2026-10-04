<script>
import { ChatLineRound, DataAnalysis, Refresh, Promotion } from '@element-plus/icons-vue'

import AppShell from '../components/AppShell.vue'
import AgentSteps from '../components/AgentSteps.vue'
import AnalysisResult from '../components/AnalysisResult.vue'
import ReportWorkbench from '../components/ReportWorkbench.vue'
import PromptComposer from '../components/PromptComposer.vue'
import UploadQueue from '../components/UploadQueue.vue'
import DocumentCandidatePreview from '../components/DocumentCandidatePreview.vue'
import { filesApi } from '../api/files'
import { useDatasetStore } from '../stores/datasets'
import SemanticMappingEditor from '../components/SemanticMappingEditor.vue'
import { workspaceApi } from '../api/workspace'
import { mapState } from 'pinia'
import { useAnalysisStore } from '../stores/analysis'
import { analysisApi } from '../api/analysis'
import { datasetApi } from '../api/datasets'
import ArtifactWorkspace from '../components/ArtifactWorkspace.vue'
import MentionPicker from '../components/MentionPicker.vue'
import { useWorkspaceStore } from '../stores/workspace'

export default {
  name: 'AnalysisWorkspaceView',
  components: { ArtifactWorkspace, MentionPicker, AppShell, AgentSteps, AnalysisResult, ReportWorkbench, PromptComposer, UploadQueue, DocumentCandidatePreview, SemanticMappingEditor, ChatLineRound, DataAnalysis, Refresh, Promotion },
  data() {
    return {
      dataset: null,
      datasetChoices: [],
      selectedDatasetId: null,
      choosingDataset: false,
      datasetSearchToken: 0,
      datasetSelectionToken: 0,
      cancelRequested: false,
      reportDialogVisible: false,
      selectedReportId: null, restoredAnalysis: null,
      artifactPanelOpen: false,
      artifactPanelMaximized: false,
      artifactPanelWidth: 560,
      resizePointer: null,
      sessionId: null,
      messages: [],
      messageCursor: null,
      messageCount: 0,
      olderLoading: false,
      question: '',
      loading: false,
      initializing: true,
      errorMessage: '',
      controller: null,
      sessionCreation: null,
      attachedDatasets: [], attachedDocuments: [], documentFileId: null, documentPage: 1, documentTotal: 0,
      uploadBusy: false,
      attachmentBindings: 0,
      attachmentChain: Promise.resolve(),
      capabilities: {},
      catalog: { categories: [], items: [] },
      capabilityError: '',
      runOptions: { depth: 'STANDARD', category: '', profile_ids: [], model_id: null },
      additionalInputIds: [],
    }
  },
  computed: {
    ...mapState(useAnalysisStore, { activeTrace: 'trace', activeResult: 'result' }),
    ...mapState(useWorkspaceStore, { workspaceArtifacts: 'items', workspaceReports: 'reports' }),
    analysisLayoutStyle() { return { '--artifact-panel-width': `${this.artifactPanelWidth}px` } },
    latestEvidence() {
      const value = [...this.messages].reverse().find(message => message.evidence && !['create','export'].includes(message.evidence.report?.operation))?.evidence || null
      return this.restoredAnalysis && (!value || this.restoredAnalysis.record_id > value.record_id) ? this.restoredAnalysis : value
    },
    isLanding() { return !this.messages.length && !this.loading && !this.workspaceArtifacts?.length && !this.workspaceReports?.length },
    canCreateReport() { return Boolean(this.sessionId && this.latestEvidence?.record_id && this.latestEvidence?.dataset_id && this.latestEvidence?.dataset_version_id && ['succeeded', 'partial'].includes(this.latestEvidence.status)) },
    runningLabel() {
      if (this.cancelRequested) return '正在取消任务…'
      if (!this.activeResult?.agent_response?.intent) return '正在理解问题…'
      if (!this.activeTrace?.plan) return '正在规划分析…'
      const steps = this.activeTrace.plan.steps || []
      const running = steps.find((step) => step.status === 'RUNNING')
      if (running) return running.tool_name === 'generate_chart' ? '正在绘制图表…' : '正在计算数据…'
      if (steps.length && steps.every((step) => ['COMPLETED', 'SKIPPED', 'FAILED'].includes(step.status))) return '正在总结结果…'
      return '正在执行分析…'
    },
  },
  watch: {
    '$route.params.sessionId'(value) {
      if ((value ? Number(value) : null) !== this.sessionId) this.initializeWorkspace()
    },
  },
  created() { this.restorePanelPreference(); this.initializeWorkspace() },
  beforeUnmount() { this.controller?.abort(); this.endPanelResize() },
  methods: {
    restorePanelPreference() {
      try {
        const saved = JSON.parse(localStorage.getItem('datalens:artifact-panel') || '{}')
        if (typeof saved.open === 'boolean') this.artifactPanelOpen = saved.open
        if (Number.isFinite(saved.width)) this.artifactPanelWidth = Math.max(420, Math.min(720, saved.width))
      } catch { /* 浏览器禁用本地存储时使用默认布局 */ }
    },
    savePanelPreference() {
      try { localStorage.setItem('datalens:artifact-panel', JSON.stringify({ open: this.artifactPanelOpen, width: this.artifactPanelWidth })) }
      catch { /* 布局偏好不可持久化时仍可在本次工作区使用 */ }
    },
    toggleArtifactPanel() {
      this.artifactPanelOpen = !this.artifactPanelOpen
      this.artifactPanelMaximized = false
      this.savePanelPreference()
    },
    toggleArtifactPanelSize() {
      this.artifactPanelMaximized = !this.artifactPanelMaximized
    },
    startPanelResize(event) {
      if (this.artifactPanelMaximized) return
      this.resizePointer = { id: event.pointerId, x: event.clientX, width: this.artifactPanelWidth }
      event.currentTarget.setPointerCapture(event.pointerId)
      event.preventDefault()
    },
    movePanelResize(event) {
      if (!this.resizePointer || event.pointerId !== this.resizePointer.id) return
      const delta = this.resizePointer.x - event.clientX
      this.artifactPanelWidth = Math.max(420, Math.min(720, this.resizePointer.width + delta))
    },
    endPanelResize() {
      if (!this.resizePointer) return
      this.resizePointer = null
      this.savePanelPreference()
    },
    async initializeWorkspace() {
      // 路由切换只停止客户端轮询，后台任务仍可在原会话恢复。
      this.$refs.uploadQueue?.stop()
      this.controller?.abort()
      const controller = new AbortController()
      this.controller = controller
      this.loading = false
      this.uploadBusy = false
      this.initializing = true
      this.errorMessage = ''
      this.messages = []
      useWorkspaceStore().reset(); this.restoredAnalysis = null; this.selectedReportId = null; this.reportDialogVisible = false
      this.dataset = null
      this.sessionId = null
      this.sessionCreation = null
      this.attachedDatasets = []; this.attachedDocuments = []; this.documentFileId = null; this.documentPage = 1
      this.additionalInputIds = []
      this.runOptions = { depth: 'STANDARD', category: '', profile_ids: [], model_id: null }
      this.attachmentBindings = 0
      this.attachmentChain = Promise.resolve()
      this.olderLoading = false
      this.messageCursor = null
      this.cancelRequested = false
      this.choosingDataset = false
      let historyMessages = []
      try {
        const queryDatasetId = this.$route.query.datasetId
        const routeSessionId = this.$route.params.sessionId
        if (!routeSessionId) {
          this.dataset = queryDatasetId ? await datasetApi.detail(queryDatasetId, { signal: controller.signal }) : null
          if (!this.isCurrent(controller)) return
        } else {
          this.sessionId = Number(routeSessionId)
          const history = await analysisApi.session(this.sessionId, {}, { signal: controller.signal })
          if (!this.isCurrent(controller)) return
          const datasetId = history.dataset?.id || queryDatasetId
          const dataset = datasetId ? await datasetApi.detail(datasetId, { signal: controller.signal }) : null
          if (!this.isCurrent(controller)) return
          this.dataset = dataset
          historyMessages = history.messages
          this.messages = history.messages.map(this.toChatMessage)
          const attachments = await Promise.all((history.session?.attached_dataset_ids || []).map(id => datasetApi.detail(id, { signal: controller.signal })))
          if (!this.isCurrent(controller)) return
          this.attachedDatasets = attachments
          await this.loadDocuments(controller)
          const previousOptions = [...history.messages].reverse().find(message => message.analysis_record?.request_options)?.analysis_record.request_options
          if (previousOptions) {
            this.runOptions = { ...this.runOptions, ...previousOptions }
            this.additionalInputIds = (previousOptions.inputs || []).map(item => item.dataset_id).filter(id => id !== dataset?.id && attachments.some(item => item.id === id))
          }
          // 澄清候选以持久任务详情为准，刷新后恢复最近的待补充响应。
          const latest = this.messages.at(-1)
          if (latest?.role === 'assistant' && latest.evidence?.status === 'waiting') {
            const restored = await analysisApi.run(latest.evidence.record_id, { signal: controller.signal })
            if (!this.isCurrent(controller)) return
            latest.evidence = restored
          }
          this.messageCursor = history.next_cursor
          this.messageCount = history.message_count
        }
        this.selectedDatasetId = this.dataset?.id ?? null
        const available = await datasetApi.list({ status: 'ready', page: 1, page_size: 50 }, { signal: controller.signal })
        if (!this.isCurrent(controller)) return
        this.datasetChoices = available?.items || []
        if (this.dataset && !this.datasetChoices.some((item) => item.id === this.dataset.id)) this.datasetChoices.push(this.dataset)
        if (this.$route.query.question) this.question = String(this.$route.query.question)
        await this.loadCapabilities(controller)
        if (!this.isCurrent(controller)) return
        if (this.sessionId && this.capabilities.artifact_references) {
          await useWorkspaceStore().load(this.sessionId, { signal: controller.signal })
          if (!this.isCurrent(controller)) return
          this.restoredAnalysis = useWorkspaceStore().latestAnalysis
        }
        if (this.latestEvidence || this.workspaceArtifacts.length || this.workspaceReports.length) this.artifactPanelOpen = true
        else this.artifactPanelOpen = false
        const pending = useAnalysisStore().restore(this.sessionId, this.dataset?.id ?? null, historyMessages)
        if (pending) {
          this.loading = true
          this.artifactPanelOpen = true
          this.resumeTask(controller).catch((error) => { if (this.isCurrent(controller) && error.name !== 'AbortError' && error.code !== 'ERR_CANCELED') this.errorMessage = error.message }).finally(() => { if (this.isCurrent(controller)) this.loading = false })
        }
      } catch (error) {
        if (this.isCurrent(controller) && error.name !== 'AbortError' && error.code !== 'ERR_CANCELED') this.errorMessage = error.message || '工作区加载失败'
      } finally {
        if (this.isCurrent(controller)) this.initializing = false
        if (this.isCurrent(controller) && this.$route.query.run === '1' && this.question) {
          const query = { ...this.$route.query }
          delete query.run
          this.$router.replace({ query })
          this.$nextTick(() => this.submitQuestion())
        }
      }
    },
    async loadCapabilities(controller) {
      const responses = await Promise.allSettled([workspaceApi.capabilities({ signal: controller.signal }), workspaceApi.profiles({}, { signal: controller.signal })])
      if (!this.isCurrent(controller)) return
      if (responses[0].status === 'fulfilled') this.capabilities = responses[0].value
      if (responses[1].status === 'fulfilled') this.catalog = responses[1].value
      this.capabilityError = responses.some(response => response.status === 'rejected') ? '能力目录暂时不可用，可继续使用现有数据分析，稍后重试。' : ''
    },
    async ensureSession(controller = this.controller) {
      if (this.sessionId) return this.sessionId
      if (this.sessionCreation) return this.sessionCreation
      const creation = analysisApi.createSession({ dataset_id: this.dataset?.id ?? null }, { signal: controller.signal }).then(session => {
        if (!this.isCurrent(controller)) throw new DOMException('Workspace changed', 'AbortError')
        this.sessionId = session.id
        this.$router.replace({ name: 'analysis', params: { sessionId: session.id }, query: { ...this.$route.query } })
        return session.id
      })
      this.sessionCreation = creation
      try { return await creation } finally { if (this.sessionCreation === creation) this.sessionCreation = null }
    },
    async loadDocuments(controller = this.controller) {
      try { const value = await filesApi.list({ session_id: this.sessionId, page: this.documentPage, page_size: 20 }, { signal: controller.signal }); if (this.isCurrent(controller)) { this.attachedDocuments = (value.items || []).filter(item => ['txt','pdf','docx'].includes(item.type)); this.documentTotal = value.total || 0 } } catch (error) { if (this.isCurrent(controller)) this.errorMessage = error.message || '文档附件恢复失败' }
    },
    documentReady(file) { this.documentFileId = file.id; this.loadDocuments() },
    async extractedDataset(dataset) { try { const ready = await useDatasetStore().upload(null, { datasetId: dataset.id, signal: this.controller.signal }); await this.attachDataset(ready) } catch (error) { this.errorMessage = error.message || '候选表解析失败，可在数据集页面查看' } },
    startUpload() {
      this.ensureSession().catch(error => { if (error.name !== 'AbortError' && error.code !== 'ERR_CANCELED') this.errorMessage = error.message || '会话创建失败；文件仍保留在数据集页面。' })
    },
    attachDataset(dataset) {
      const controller = this.controller
      this.attachmentBindings++
      this.attachmentChain = this.attachmentChain.then(() => this.bindDataset(dataset, controller)).finally(() => { if (this.isCurrent(controller)) this.attachmentBindings-- })
      return this.attachmentChain
    },
    async bindDataset(dataset, controller) {
      if (!this.isCurrent(controller)) return
      try {
        await this.ensureSession(controller)
        if (!this.isCurrent(controller)) return
        const next = [...this.attachedDatasets.filter(item => item.id !== dataset.id), dataset]
        await analysisApi.updateSession(this.sessionId, { attached_dataset_ids: next.map(item => item.id) }, { signal: controller.signal })
        if (!this.isCurrent(controller)) return
        this.attachedDatasets = next
        if (!this.datasetChoices.some(item => item.id === dataset.id)) this.datasetChoices.push(dataset)
        if (!this.dataset) { this.dataset = dataset; this.selectedDatasetId = dataset.id }
        return true
      } catch (error) {
        if (this.isCurrent(controller)) this.errorMessage = `文件已上传，但会话绑定失败：${error.message}。可在数据集列表选择后继续分析。`
        return false
      }
    },
    removeAttachment(id) {
      if (!id || !this.sessionId) return
      const controller = this.controller
      this.attachmentBindings++
      this.attachmentChain = this.attachmentChain.then(async () => {
        if (!this.isCurrent(controller)) return
        const next = this.attachedDatasets.filter(item => item.id !== id)
        try {
          await analysisApi.updateSession(this.sessionId, { attached_dataset_ids: next.map(item => item.id) }, { signal: controller.signal })
          if (this.isCurrent(controller)) { this.attachedDatasets = next; this.$refs.uploadQueue?.forgetDataset(id) }
        } catch (error) { if (this.isCurrent(controller)) this.errorMessage = error.message || '附件移除失败' }
      }).finally(() => { if (this.isCurrent(controller)) this.attachmentBindings-- })
      return this.attachmentChain
    },
    async submitQuestion() {
      const question = this.question.trim()
      if (!question || this.loading || this.initializing || this.choosingDataset || this.uploadBusy || this.attachmentBindings) return
      this.loading = true
      const sessionController = this.controller
      try { await this.ensureSession(sessionController) }
      catch (error) { if (this.isCurrent(sessionController)) { this.loading = false; this.errorMessage = error.message || '会话创建失败' }; return }
      if (!this.isCurrent(sessionController)) return
      this.controller?.abort()
      this.controller = new AbortController()
      const controller = this.controller
      this.loading = true
      this.artifactPanelOpen = true
      this.cancelRequested = false
      this.errorMessage = ''
      this.question = ''
      const userMessage = { id: crypto.randomUUID(), role: 'user', content: question }
      this.messages.push(userMessage)
      try {
        const store = useAnalysisStore()
        const options = this.capabilities.profile_execution && this.dataset ? {
          ...this.runOptions, category: this.runOptions.category || null,
          inputs: [this.dataset.id, ...this.additionalInputIds.filter(id => id !== this.dataset.id && this.attachedDatasets.some(item => item.id === id))].map((id, index) => {
            const versions = this.workspaceArtifacts.filter(item => (this.runOptions.artifact_refs || []).includes(item.id || item.artifact_id)).flatMap(item => item.dataset_versions || []).filter(item => item.dataset_id === id)
            return { alias: index === 0 ? 'primary' : `input_${id}`, dataset_id: id, ...(versions[0]?.dataset_version_id ? { dataset_version_id: versions[0].dataset_version_id } : {}) }
          }),
        } : {}
        await store.submit({ session_id: this.sessionId, dataset_id: this.dataset?.id ?? null, question, ...options }, false, { signal: controller.signal })
        if (!this.isCurrent(controller)) return
        const result = await store.watchRun(controller.signal)
        if (!result || !this.isCurrent(controller)) return
        if (result.dataset_id && this.dataset?.id !== result.dataset_id) await this.chooseDataset(result.dataset_id)
        userMessage.evidence = result
        this.messages.push({ id: result.message_id || result.record_id, role: 'assistant', content: result.answer || result.error_message, status: result.status, evidence: result })
        if (this.capabilities.artifact_references) await useWorkspaceStore().load(this.sessionId, { signal: controller.signal })
      } catch (error) {
        if (!this.isCurrent(controller) || error.name === 'AbortError' || error.code === 'ERR_CANCELED') return
        this.question = question
        userMessage.error = error.message || '分析失败，请保留问题后重试。'
        userMessage.errorCode = error.code
      } finally {
        if (this.isCurrent(controller)) this.loading = false
      }
    },
    toChatMessage(message) {
      const record = message.analysis_record
      const evidence = record ? {
        record_id: record.id,
        dataset_id: record.dataset_id,
        dataset_version_id: record.dataset_version_id,
        plan: record.plan,
        report: record.report,
        status: record.status,
        answer: record.final_answer,
        execution_time: (record.execution_time_ms || 0) / 1000,
        tool_calls: record.tool_calls || [],
        tool_result: record.tool_result,
        chart: record.chart,
        summary_error: record.status === 'partial' ? 'SUMMARY_UNAVAILABLE' : null,
      } : null
      return {
        id: message.id,
        role: message.role,
        content: message.content,
        status: message.status,
        evidence: message.role === 'assistant' ? evidence : null,
        error: message.status === 'failed' ? record?.error_message || '分析失败，请稍后重试' : '',
      }
    },
    async loadOlderMessages() {
      if (!this.messageCursor || this.olderLoading) return
      const controller = this.controller
      this.olderLoading = true
      try {
        const page = await analysisApi.session(this.sessionId, { message_cursor: this.messageCursor, message_limit: 50 }, { signal: controller.signal })
        if (!this.isCurrent(controller)) return
        this.messages = [...page.messages.map(this.toChatMessage), ...this.messages]
        this.messageCursor = page.next_cursor
      } catch (error) {
        if (this.isCurrent(controller) && error.code !== 'ERR_CANCELED' && error.name !== 'AbortError') this.errorMessage = error.message || '更早的消息加载失败'
      } finally {
        if (this.isCurrent(controller)) this.olderLoading = false
      }
    },
    handleEnter(event) {
      if (!event.isComposing) { event.preventDefault(); this.submitQuestion() }
    },
    formatDuration(seconds) {
      return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(2)} 秒`
    },
    showValue(value) { return value === null || value === undefined ? '—' : String(value) },
    openReport(id = null) { this.selectedReportId = id; this.reportDialogVisible = true },
    referenceArtifact(item) {
      const id = item.id || item.artifact_id
      this.runOptions = { ...this.runOptions, artifact_refs: [...new Set([...(this.runOptions.artifact_refs || []), id])].slice(0,10) }
    },
    async reportsChanged() { if (this.sessionId && this.capabilities.artifact_references) await useWorkspaceStore().load(this.sessionId, { signal: this.controller.signal }) },
    async searchDatasets(query) {
      const token = ++this.datasetSearchToken
      const controller = this.controller
      try {
        const result = await datasetApi.list({ status: 'ready', q: query || undefined, page: 1, page_size: 50 }, { signal: controller.signal })
        if (!this.isCurrent(controller) || token !== this.datasetSearchToken) return
        this.datasetChoices = result?.items || []
        if (this.dataset && !this.datasetChoices.some((item) => item.id === this.dataset.id)) this.datasetChoices.push(this.dataset)
      } catch (error) {
        if (this.isCurrent(controller)) this.errorMessage = error.message || '数据集搜索失败'
      }
    },
    async chooseDataset(id) {
      const selection = ++this.datasetSelectionToken
      if (!id) { this.dataset = null; this.selectedDatasetId = null; return }
      const controller = this.controller
      this.choosingDataset = true
      try {
        const dataset = await datasetApi.detail(id, { signal: controller.signal })
        if (!this.isCurrent(controller) || selection !== this.datasetSelectionToken) return
        // 先保存授权会话绑定，再让字段编辑器读取新数据集。
        if (this.sessionId && this.capabilities.profile_execution && !this.attachedDatasets.some(item => item.id === dataset.id)) {
          const bound = await this.attachDataset(dataset)
          if (!bound) { this.selectedDatasetId = this.dataset?.id ?? null; return }
        }
        if (!this.isCurrent(controller) || selection !== this.datasetSelectionToken) return
        this.dataset = dataset
        this.selectedDatasetId = dataset.id
        if (!this.datasetChoices.some((item) => item.id === dataset.id)) this.datasetChoices.push(dataset)
        this.$router.replace({ query: { ...this.$route.query, datasetId: String(dataset.id) } })
      } catch (error) {
        if (this.isCurrent(controller) && selection === this.datasetSelectionToken) { this.errorMessage = error.message || '数据集加载失败'; this.selectedDatasetId = this.dataset?.id ?? null }
      } finally { if (this.isCurrent(controller) && selection === this.datasetSelectionToken) this.choosingDataset = false }
    },
    async cancelTask() {
      if (!this.loading || this.cancelRequested) return
      this.cancelRequested = true
      try { await useAnalysisStore().cancel() }
      catch (error) { this.cancelRequested = false; this.errorMessage = error.message || '取消请求失败' }
    },
    useClarificationDataset(id) {
      const lastQuestion = [...this.messages].reverse().find((message) => message.role === 'user')
      this.question = lastQuestion?.content || this.question
      this.chooseDataset(id)
    },
    isCurrent(controller) { return this.controller === controller && !controller.signal.aborted },
    async resumeTask(controller = this.controller) {
      const store = useAnalysisStore()
      if (!store.pending.record_id) await store.submit({}, true, { signal: controller.signal })
      if (!this.isCurrent(controller)) return
      const result = await store.watchRun(controller.signal)
      if (result?.dataset_id && this.isCurrent(controller) && this.dataset?.id !== result.dataset_id) await this.chooseDataset(result.dataset_id)
      if (result && this.isCurrent(controller) && !this.messages.some((message) => message.role === 'assistant' && message.evidence?.record_id === result.record_id)) this.messages.push({ id: result.message_id || result.record_id, role: 'assistant', content: result.answer || result.error_message, status: result.status, evidence: result })
      if (result && this.isCurrent(controller) && this.capabilities.artifact_references) await useWorkspaceStore().load(this.sessionId, { signal: controller.signal })
    },
    async retryMessage(message) {
      if (message.errorCode === 'NETWORK_ERROR' && useAnalysisStore().pending) {
        this.controller?.abort(); this.controller = new AbortController(); this.loading = true; message.error = ''
        const controller = this.controller
        try { await this.resumeTask(controller) }
        catch (error) { if (this.isCurrent(controller) && error.code !== 'ERR_CANCELED' && error.name !== 'AbortError') { message.error = error.message; message.errorCode = error.code } }
        finally { if (this.isCurrent(controller)) this.loading = false }
      } else { this.question = message.content; this.submitQuestion() }
    },
  },
}
</script>

<template>
  <AppShell>
    <section v-if="!isLanding" class="analysis-heading">
      <div>
        <p class="eyebrow">真实数据计算 · 可核对执行证据</p>
        <h1>智能分析</h1>
        <p class="page-intro">{{ dataset?.original_name || '可先聊天，分析前请选择数据集' }}<span v-if="dataset"> · {{ dataset.row_count }} 行 · {{ dataset.column_count }} 列</span></p>
      </div>
      <el-button v-if="dataset" plain @click="$router.push(`/datasets/${dataset.id}`)">数据集详情</el-button>
    </section>

    <div v-if="errorMessage" class="inline-error" role="alert"><span>{{ errorMessage }}</span><el-button text type="primary" @click="initializeWorkspace"><el-icon><Refresh /></el-icon>重试</el-button></div>
    <p v-if="capabilityError" class="capability-warning" role="status">{{ capabilityError }} <button type="button" @click="loadCapabilities(controller)">重试目录</button></p>
    <section v-if="initializing" class="panel analysis-loading" aria-live="polite"><span class="large-loader"></span><h2>正在准备分析工作区</h2></section>
    <section v-else class="analysis-layout" :class="{ 'panel-hidden': !artifactPanelOpen, 'panel-maximized': artifactPanelMaximized, 'workspace-landing': isLanding }" :style="analysisLayoutStyle">
      <div class="panel conversation-panel">
        <header v-if="!isLanding" class="conversation-header"><div class="conversation-title"><span class="analysis-mark"><el-icon><DataAnalysis /></el-icon></span><div><h2>分析对话</h2><p>基于服务器端计算结果回答</p></div></div><div class="conversation-header-actions"><el-tag v-if="sessionId" effect="plain" round>会话 #{{ sessionId }}</el-tag><el-button v-if="!artifactPanelOpen" text @click="toggleArtifactPanel">打开工件面板</el-button></div></header>
        <div class="analysis-dataset-picker"><label for="analysis-dataset">当前数据集</label><el-select id="analysis-dataset" v-model="selectedDatasetId" filterable remote :remote-method="searchDatasets" placeholder="选择数据集（聊天可留空）" :disabled="loading" @change="chooseDataset"><el-option v-for="option in datasetChoices" :key="option.id" :label="option.original_name" :value="option.id" /></el-select></div>

        <div class="conversation-stream" aria-live="polite" aria-relevant="additions text">
          <el-button v-if="messageCursor" class="load-older-button" text :loading="olderLoading" @click="loadOlderMessages">加载更早的消息</el-button>
          <div v-if="messages.length === 0" class="conversation-empty">
            <p class="workspace-wordmark">DATA ANALYSIS WORKSPACE</p>
            <h1>Hey！今天想分析什么数据？</h1>
            <p>上传数据，提出业务问题，让分析从这里开始。</p>
          </div>
          <article v-for="message in messages" :key="message.id" class="chat-message" :class="`message-${message.role}`">
            <div class="message-role">{{ message.role === 'user' ? '你' : 'DataLens Agent' }}</div>
            <p v-if="message.content" class="message-content">{{ message.content }}</p>
            <div v-if="message.role === 'assistant' && message.evidence?.agent_response?.clarification?.candidate_dataset_ids?.length" class="clarification-choices"><el-button v-for="id in message.evidence.agent_response.clarification.candidate_dataset_ids" :key="id" plain size="small" @click="useClarificationDataset(id)">选择 {{ datasetChoices.find((item) => item.id === id)?.original_name || `数据集 #${id}` }}</el-button></div>
            <div v-if="message.evidence?.status === 'cancelled'" class="partial-note" role="status">任务已取消，已完成的结果仍可查看。</div>
            <div v-if="message.evidence?.status === 'partial'" class="partial-note" role="status">分析部分完成，下面保留已完成的真实计算结果。</div>
            <div v-if="message.error" class="message-error" role="alert"><span>{{ message.error }}</span><el-button text type="primary" @click="retryMessage(message)">保留问题并重试</el-button></div>
          </article>
          <div v-if="loading" class="agent-pending" role="status"><span class="status-pulse"></span>{{ runningLabel }}<el-button text type="danger" :disabled="cancelRequested" @click="cancelTask">取消任务</el-button></div>
        </div>

        <PromptComposer v-model="question" :busy="loading || choosingDataset" :uploading="uploadBusy || attachmentBindings > 0" :catalog="catalog" :capabilities="capabilities" :options="runOptions" @option-change="runOptions = { ...runOptions, ...$event }" @submit="submitQuestion" @upload="$refs.uploadQueue.addFiles($event)" @templates="$router.push('/templates')">
          <MentionPicker v-if="capabilities.artifact_references" :items="workspaceArtifacts" :model-value="runOptions.artifact_refs || []" :busy="loading" @update:model-value="runOptions = { ...runOptions, artifact_refs: $event }" />
          <UploadQueue ref="uploadQueue" :session-id="Number(sessionId) || undefined" :prepare-session="ensureSession" @document="documentReady" @document-hidden="documentFileId === $event && (documentFileId = null)" :formats="[...(capabilities.file_formats || []), ...(capabilities.document_formats || [])]" :attached-ids="attachedDatasets.map(item => item.id)" :max-files="capabilities.max_files || 10" :max-bytes="capabilities.max_upload_bytes || 20971520" @busy="uploadBusy = $event" @started="startUpload" @ready="attachDataset" @removed="removeAttachment" />
          <div v-if="attachedDocuments.length" class="session-attachments" aria-label="会话文档附件"><el-button v-for="file in attachedDocuments" :key="file.id" @click="documentFileId = file.id">{{ file.name }} · 文档</el-button><el-button :disabled="documentPage === 1" @click="documentPage--; loadDocuments()">上一页文档</el-button><el-button :disabled="documentPage * 20 >= documentTotal" @click="documentPage++; loadDocuments()">下一页文档</el-button></div>
          <div v-if="documentFileId"><DocumentCandidatePreview :file-id="documentFileId" :session-id="Number(sessionId)" @ready="extractedDataset" /><el-button @click="documentFileId = null">收起附件预览</el-button><p class="caption">收起只关闭预览，文档仍在会话中，刷新可恢复。</p></div>
          <div v-if="attachedDatasets.length" class="session-attachments" aria-label="会话数据附件"><span v-for="item in attachedDatasets" :key="item.id"><button type="button" :disabled="loading" @click="chooseDataset(item.id)">{{ item.original_name }}{{ dataset?.id === item.id ? ' · 当前' : '' }}</button><button type="button" :disabled="loading || attachmentBindings > 0" :aria-label="`移除附件 ${item.original_name}`" @click="removeAttachment(item.id)">×</button></span></div>
        </PromptComposer>
        <fieldset v-if="capabilities.multi_dataset_execution && dataset && attachedDatasets.some(item => item.id !== dataset.id)" class="analysis-inputs"><legend>同时分析其他附件</legend><label v-for="item in attachedDatasets.filter(item => item.id !== dataset.id)" :key="item.id"><input v-model="additionalInputIds" type="checkbox" :value="item.id" :disabled="loading || choosingDataset" />{{ item.original_name }}</label><p class="caption">所选附件会固定版本参与分析；需要合并数据时，可在数据集页按关联键预览并确认保存。</p></fieldset>
        <SemanticMappingEditor v-if="capabilities.profile_execution && sessionId && dataset" :session-id="Number(sessionId)" :dataset-id="dataset.id" :busy="loading || choosingDataset" />
        <div v-if="isLanding" class="workspace-suggestions"><button type="button" @click="question = '帮我分析一下这个表'">探索这份数据</button><button type="button" @click="question = '检查缺失值、重复数据和异常值'">检查数据质量</button><button type="button" @click="question = '按地区汇总销售额，并生成柱状图'">比较业务表现</button><button type="button" @click="$router.push('/templates')">浏览分析模板 ↗</button></div>
        <p v-if="!dataset && isLanding" class="workspace-help">可先聊天，分析前请选择数据集或上传文件。</p>
      </div>

      <button v-if="artifactPanelOpen" type="button" class="artifact-panel-backdrop" aria-label="关闭工件面板" @click="toggleArtifactPanel"></button>
      <aside v-if="artifactPanelOpen" class="panel evidence-panel artifact-panel" aria-label="工件与分析证据">
        <div v-if="!artifactPanelMaximized" class="artifact-panel-resizer" tabindex="0" role="separator" aria-label="调整工件面板宽度" aria-orientation="vertical" :aria-valuenow="artifactPanelWidth" aria-valuemin="420" aria-valuemax="720" @keydown.left.prevent="artifactPanelWidth = Math.min(720, artifactPanelWidth + 20); savePanelPreference()" @keydown.right.prevent="artifactPanelWidth = Math.max(420, artifactPanelWidth - 20); savePanelPreference()" @pointerdown="startPanelResize" @pointermove="movePanelResize" @pointerup="endPanelResize" @pointercancel="endPanelResize"><span></span></div>
        <div class="evidence-panel-heading"><span class="evidence-dot"></span><div><h2>工件与证据</h2><p>图表、结果表和工具轨迹</p></div><el-button v-if="canCreateReport" size="small" plain @click="openReport()">生成报告</el-button><el-button text aria-label="最大化工件面板" @click="toggleArtifactPanelSize">{{ artifactPanelMaximized ? '还原' : '展开' }}</el-button><el-button text aria-label="关闭工件面板" @click="toggleArtifactPanel">关闭</el-button></div>
        <p v-if="loading && activeResult?.progress?.total" class="caption">已完成 {{ activeResult.progress.completed }} / {{ activeResult.progress.total }} 步</p>
        <AgentSteps :trace="activeTrace || (latestEvidence?.plan ? { plan: latestEvidence.plan, steps: latestEvidence.tool_calls } : null)" :calls="loading ? [] : latestEvidence?.tool_calls || []" />
        <AnalysisResult v-if="loading && activeResult" :evidence="activeResult" />
        <AnalysisResult v-else-if="latestEvidence" :evidence="latestEvidence" />
        <ArtifactWorkspace v-if="sessionId && capabilities.artifact_references" :session-id="sessionId" @report="openReport" @reference="referenceArtifact" />
      </aside>
    </section>
    <ReportWorkbench v-if="sessionId" :key="`${sessionId}-${selectedReportId || 'new'}`" v-model="reportDialogVisible" :session-id="sessionId" :report-id="selectedReportId" :source="latestEvidence" @changed="reportsChanged" />
  </AppShell>
</template>

<style scoped>
.workspace-landing { margin: 5vh auto 0; max-width: 1100px; }
.workspace-landing .conversation-panel { min-height: 0; width: 100%; max-width: 940px; background: transparent; border: 0; box-shadow: none; overflow: visible; }
.workspace-landing .conversation-stream { min-height: 0; padding: 0; order: -2; }
.workspace-landing .conversation-empty { min-height: 160px; padding: 16px 0 30px; }
.conversation-empty h1 { font-size: clamp(22px, 2.5vw, 32px); font-weight: 550; margin: 8px 0 14px; letter-spacing: -.6px; }
.conversation-empty p { font-size: 13px; }
.conversation-empty .workspace-wordmark { color: var(--muted); font-size: 10px; letter-spacing: 2px; }
.workspace-landing .analysis-dataset-picker { order: 2; background: transparent; padding: 16px 0; border: 0; }
.conversation-panel > .prompt-composer { width: auto; margin: 12px; }
.workspace-landing .conversation-panel > .prompt-composer { width: 100%; margin: 0; }
.workspace-suggestions, .session-attachments { display: flex; flex-wrap: wrap; gap: 8px; }
.workspace-suggestions { justify-content: center; margin: 18px 0 2px; }
.workspace-suggestions button, .session-attachments button { cursor: pointer; border: 1px solid var(--line); padding: 8px 12px; border-radius: 10px; background: var(--surface); color: var(--muted); font-size: 12px; }
.workspace-suggestions button:hover, .session-attachments button:hover { color: var(--ink); background: var(--canvas); }
.session-attachments { margin-bottom: 8px; }
.workspace-help { color: var(--muted); text-align: center; font-size: 12px; }
.capability-warning { font-size: 12px; color: var(--muted); }
.analysis-inputs { border: 1px solid var(--line); border-radius: var(--radius-sm); margin: 12px 0; font-size: 12px; color: var(--muted); }
.analysis-inputs label { display: inline-flex; align-items: center; gap: 6px; margin-right: 16px; }
.capability-warning button { border: 0; background: none; color: var(--brand); cursor: pointer; }
@media (max-width: 700px) { .workspace-landing { margin-top: 10px; } .workspace-landing .conversation-empty { min-height: 135px; } }
</style>
