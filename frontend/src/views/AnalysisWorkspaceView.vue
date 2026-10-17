<script>
import { ElPopover } from 'element-plus'
import ChatMessage from '../components/ChatMessage.vue'
import { reportsApi } from '../api/reports'
import ArtifactPreview from '../components/ArtifactPreview.vue'
import AppShell from '../components/AppShell.vue'
import AnalysisScope from '../components/AnalysisScope.vue'
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
  components: { ElPopover, ChatMessage, ArtifactPreview, AnalysisScope, ArtifactWorkspace, MentionPicker, AppShell, AgentSteps, AnalysisResult, ReportWorkbench, PromptComposer, UploadQueue, DocumentCandidatePreview, SemanticMappingEditor },
  data() {
    return {
      sessionTitle: '', attachmentSettings: false, fileMenuOpen: false, stickToBottom: true, scrollObserver: null, compactViewport: false,
      previewSelection: null, previewFiles: [], previewBusy: false, previewError: '', previewController: null, reportSource: null, previewTrigger: null,
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
      retryVersions: null,
    }
  },
  computed: {
    ...mapState(useAnalysisStore, { activeTrace: 'trace', activeResult: 'result', activePending: 'pending' }),
    ...mapState(useWorkspaceStore, { workspaceArtifacts: 'items', workspaceReports: 'reports' }),
    inputDatasets() { return this.dataset ? [this.dataset, ...this.attachedDatasets.filter(item => item.id !== this.dataset.id)] : this.attachedDatasets },
    selectedReferences() { return this.workspaceArtifacts.filter(item => (this.runOptions.artifact_refs || []).includes(item.id || item.artifact_id)) },
    analysisLayoutStyle() { return { '--artifact-panel-width': `${this.artifactPanelWidth}px` } },
    latestEvidence() {
      const value = [...this.messages].reverse().find(message => message.evidence && !['create','export'].includes(message.evidence.report?.operation))?.evidence || null
      return this.restoredAnalysis && (!value || this.restoredAnalysis.record_id > value.record_id) ? this.restoredAnalysis : value
    },
    isLanding() { return !this.messages.length && !this.loading && !this.workspaceArtifacts?.length && !this.workspaceReports?.length },
    canCreateReport() { return Boolean(this.sessionId && this.latestEvidence?.record_id && this.latestEvidence?.dataset_id && this.latestEvidence?.dataset_version_id && ['succeeded', 'partial'].includes(this.latestEvidence.status)) },
    canInterrupt() { return Boolean(this.loading && this.activePending?.record_id && Number(this.activePending.session_id) === Number(this.sessionId)) },
    runningLabel() {
      if (this.cancelRequested) return '正在中断任务，等待服务端确认…'
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
  mounted() {
    document.addEventListener('keydown', this.attachmentEscape)
    this.updateViewport()
    window.addEventListener('resize', this.updateViewport)
    if (!window.ResizeObserver) return
    this.scrollObserver = new ResizeObserver(() => { if (this.stickToBottom) this.scrollLatest() })
    this.$nextTick(() => { if (this.$refs.streamContent) this.scrollObserver.observe(this.$refs.streamContent) })
  },
  updated() { if (this.$refs.streamContent) this.scrollObserver?.observe(this.$refs.streamContent) },
  created() { this.restorePanelPreference(); this.initializeWorkspace() },
  beforeUnmount() { document.removeEventListener('keydown', this.attachmentEscape); window.removeEventListener('resize', this.updateViewport); this.controller?.abort(); this.previewController?.abort(); this.scrollObserver?.disconnect(); this.endPanelResize() },
  methods: {
    restorePanelPreference() {
      try {
        const saved = JSON.parse(localStorage.getItem('datalens:artifact-panel') || '{}')
        if (Number.isFinite(saved.width)) this.artifactPanelWidth = Math.max(420, Math.min(720, saved.width))
      } catch { /* 浏览器禁用本地存储时使用默认布局 */ }
    },
    savePanelPreference() {
      try { localStorage.setItem('datalens:artifact-panel', JSON.stringify({ open: this.artifactPanelOpen, width: this.artifactPanelWidth })) }
      catch { /* 布局偏好不可持久化时仍可在本次工作区使用 */ }
    },
    toggleArtifactPanel() {
      this.previewController?.abort()
      this.artifactPanelOpen = !this.artifactPanelOpen
      this.artifactPanelMaximized = false
      this.savePanelPreference()
      this.$nextTick(() => { if (this.previewTrigger?.isConnected) this.previewTrigger.focus({ preventScroll: true }) })
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
      this.scrollObserver?.disconnect()
      this.$refs.uploadQueue?.stop()
      this.controller?.abort()
      const controller = new AbortController()
      this.controller = controller
      this.loading = false
      this.uploadBusy = false
      this.initializing = true
      this.errorMessage = ''
      this.messages = []
      this.artifactPanelOpen = false; this.previewSelection = null; this.previewController?.abort(); this.attachmentSettings = false; this.sessionTitle = ''; this.reportSource = null; this.stickToBottom = true
      useWorkspaceStore().reset(); this.restoredAnalysis = null; this.selectedReportId = null; this.reportDialogVisible = false
      this.dataset = null
      this.sessionId = null
      this.sessionCreation = null
      this.attachedDatasets = []; this.attachedDocuments = []; this.documentFileId = null; this.documentPage = 1
      this.additionalInputIds = []
      this.retryVersions = null
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
          this.sessionTitle = history.session?.title || ''
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
        this.artifactPanelOpen = false
        const pending = useAnalysisStore().restore(this.sessionId, this.dataset?.id ?? null, historyMessages)
        if (pending) {
          this.loading = true
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
      this.attachmentSettings = false
      this.fileMenuOpen = false
      this.stickToBottom = true
      this.cancelRequested = false
      this.errorMessage = ''
      this.question = ''
      this.sessionTitle ||= question
      const userMessage = { id: crypto.randomUUID(), role: 'user', content: question }
      const retryVersions = this.retryVersions || {}
      this.retryVersions = null
      this.messages.push(userMessage)
      this.$nextTick(() => this.scrollLatest())
      try {
        const store = useAnalysisStore()
        const options = this.capabilities.profile_execution && this.dataset ? {
          ...this.runOptions, category: this.runOptions.category || null,
          inputs: [this.dataset.id, ...this.additionalInputIds.filter(id => id !== this.dataset.id && this.attachedDatasets.some(item => item.id === id))].map((id, index) => {
            const versions = this.workspaceArtifacts.filter(item => (this.runOptions.artifact_refs || []).includes(item.id || item.artifact_id)).flatMap(item => item.dataset_versions || []).filter(item => item.dataset_id === id)
            const version = retryVersions[id] || versions[0]?.dataset_version_id
            return { alias: index === 0 ? 'primary' : `input_${id}`, dataset_id: id, ...(version ? { dataset_version_id: version } : {}) }
          }),
        } : {}
        await store.submit({ session_id: this.sessionId, dataset_id: this.dataset?.id ?? null, ...(retryVersions[this.dataset?.id] ? { dataset_version_id: retryVersions[this.dataset.id] } : {}), question, ...options }, false, { signal: controller.signal })
        if (!this.isCurrent(controller)) return
        const result = await store.watchRun(controller.signal)
        if (!result || !this.isCurrent(controller)) return
        if (result.dataset_id && this.dataset?.id !== result.dataset_id) await this.chooseDataset(result.dataset_id)
        this.messages.push({ id: result.message_id || result.record_id, role: 'assistant', content: result.answer || result.error_message, status: result.status, evidence: result })
        if (this.capabilities.artifact_references) await useWorkspaceStore().load(this.sessionId, { signal: controller.signal })
      } catch (error) {
        if (!this.isCurrent(controller) || error.name === 'AbortError' || error.code === 'ERR_CANCELED') return
        this.question = question
        userMessage.error = error.message || '分析失败，请保留问题后重试。'
        userMessage.errorCode = error.code
        userMessage.errorInfo = error.info
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
        error_info: record.error_info,
        error_code: record.error_code,
        error_message: record.error_message,
        analysis_context: record.analysis_context,
        request_options: record.request_options,
        summary_error: record.status === 'partial' ? 'SUMMARY_UNAVAILABLE' : null,
      } : null
      return {
        id: message.id,
        role: message.role,
        content: message.content,
        status: message.status,
        evidence: message.role === 'assistant' ? evidence : null,
        error: message.role === 'assistant' && message.status === 'failed' ? record?.error_message || '分析失败，请稍后重试' : '',
        errorInfo: message.role === 'assistant' ? record?.error_info : null,
      }
    },
    async loadOlderMessages() {
      if (!this.messageCursor || this.olderLoading) return
      const controller = this.controller
      this.olderLoading = true
      const scroll = this.$refs.stream
      const oldHeight = scroll?.scrollHeight || 0
      const oldTop = scroll?.scrollTop || 0
      this.stickToBottom = false
      try {
        const page = await analysisApi.session(this.sessionId, { message_cursor: this.messageCursor, message_limit: 50 }, { signal: controller.signal })
        if (!this.isCurrent(controller)) return
        this.messages = [...page.messages.map(this.toChatMessage), ...this.messages]
        this.messageCursor = page.next_cursor
        await this.$nextTick()
        if (scroll) scroll.scrollTop = oldTop + scroll.scrollHeight - oldHeight
      } catch (error) {
        if (this.isCurrent(controller) && error.code !== 'ERR_CANCELED' && error.name !== 'AbortError') this.errorMessage = error.message || '更早的消息加载失败'
      } finally {
        if (this.isCurrent(controller)) this.olderLoading = false
      }
    },
    onScroll() { const el = this.$refs.stream; if (el) this.stickToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80 },
    scrollLatest() { const el = this.$refs.stream; if (el) el.scrollTop = el.scrollHeight },
    returnToLatest() { this.stickToBottom = true; this.scrollLatest() },
    attachmentEscape(event) { if (event.key === 'Escape' && this.fileMenuOpen) { event.stopPropagation(); this.closeFilesMenu() } },
    focusAttachmentMenu() { document.querySelector('.attachment-menu button')?.focus({ preventScroll: true }) },
    updateViewport() { this.compactViewport = window.innerWidth <= 1100 },
    previewKeydown(event) {
      if (event.key === 'Escape') { event.stopPropagation(); this.toggleArtifactPanel(); return }
      if (event.key !== 'Tab' || !this.compactViewport) return
      const controls = [...event.currentTarget.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), iframe, [tabindex="0"]')].filter(el => el.getClientRects().length)
      const target = event.shiftKey ? controls.at(-1) : controls[0]
      if (controls.length && document.activeElement === (event.shiftKey ? controls[0] : controls.at(-1))) { event.preventDefault(); target.focus() }
    },
    closeFilesMenu() { this.fileMenuOpen = false; this.$nextTick(() => this.$refs.addAttachment?.focus()) },
    openAttachmentSettings() { this.attachmentSettings = true; this.closeFilesMenu() },
    async openPreview(selection) {
      this.previewTrigger = document.activeElement
      this.previewController?.abort(); this.previewError = ''; this.previewBusy = false; this.previewFiles = []
      this.previewSelection = selection; this.artifactPanelOpen = true; this.artifactPanelMaximized = false
      this.$nextTick(() => this.$refs.previewClose?.focus())
      if (selection.kind !== 'table' || !selection.value?.artifact_id || !selection.evidence?.record_id) return
      const controller = new AbortController(); this.previewController = controller; this.previewBusy = true
      try {
        const page = await analysisApi.result(selection.evidence.record_id, selection.value.artifact_id, { offset: 0, limit: 100 }, { signal: controller.signal })
        if (this.previewController === controller && !controller.signal.aborted) this.previewSelection = { ...selection, value: { ...selection.value, rows: page.rows || [], columns: page.columns || selection.value.columns } }
      } catch (error) { if (!controller.signal.aborted) this.previewError = error.message || '完整数据加载失败' }
      finally { if (this.previewController === controller) this.previewBusy = false }
    },
    previewEvidence() {
      const selection = this.previewSelection
      if (!selection?.evidence) return null
      // 缩放和分页只接收被点击消息的工件，禁止回退到 latestEvidence。
      return { ...selection.evidence, error_info: null, error_message: null, status: 'succeeded', tool_result: null, chart: null,
        report: { tables: selection.kind === 'table' ? [selection.value] : [], charts: selection.kind === 'chart' ? [selection.value] : [], warnings: [] } }
    },
    async openMessageFiles(evidence) {
      this.openPreview({ kind: 'files', evidence })
      const controller = new AbortController(); this.previewController = controller; this.previewBusy = true
      try {
        const run = await analysisApi.run(evidence.record_id, { signal: controller.signal })
        // Run DTO 只包含工件身份；读取授权工件详情取得真实文件名与下载地址。
        const files = await Promise.allSettled((run.artifacts || []).map(file => reportsApi.artifact(file.artifact_id || file.id, { signal: controller.signal })))
        if (this.previewController !== controller || controller.signal.aborted) return
        this.previewFiles = files.filter(file => file.status === 'fulfilled').map(file => file.value)
        if (files.some(file => file.status === 'rejected')) this.previewError = '部分文件详情读取失败，请重新打开本轮文件。'
      } catch (error) { if (!controller.signal.aborted) this.previewError = error.message || '文件加载失败' }
      finally { if (this.previewController === controller) this.previewBusy = false }
    },
    async previewFile(file) {
      this.previewController?.abort()
      const controller = new AbortController(); this.previewController = controller; this.previewBusy = true; this.previewError = ''
      try {
        const response = await reportsApi.preview(file.artifact_id || file.id, {}, { signal: controller.signal })
        if (this.previewController === controller && !controller.signal.aborted) this.previewSelection = { ...this.previewSelection, file, filePreview: response.preview || response }
      } catch (error) { if (!controller.signal.aborted) this.previewError = error.message || '预览加载失败' }
      finally { if (this.previewController === controller) this.previewBusy = false }
    },
    handleEnter(event) {
      if (!event.isComposing) { event.preventDefault(); this.submitQuestion() }
    },
    formatDuration(seconds) {
      return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(2)} 秒`
    },
    showValue(value) { return value === null || value === undefined ? '—' : String(value) },
    openReport(id = null, source = this.latestEvidence) { this.reportSource = source; this.selectedReportId = id; this.reportDialogVisible = true },
    reportForMessage(source) { this.openReport(null, source) },
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
      if (!this.canInterrupt || this.cancelRequested) return
      const controller = this.controller
      const store = useAnalysisStore()
      const pending = store.pending
      this.cancelRequested = true
      // 保持订阅直到服务端终态，不把取消 HTTP 请求当作后台任务已经结束。
      try { await store.cancel({ signal: controller.signal }) }
      catch (error) {
        if (!this.isCurrent(controller) || !this.loading || store.pending !== pending) return
        this.cancelRequested = false
        this.errorMessage = error.message || '中断请求未能确认，请重试或重新连接查看任务状态。'
      }
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
      if (['NETWORK_ERROR', 'HTTP_REQUEST_TIMEOUT'].includes(message.errorCode) && useAnalysisStore().pending) {
        this.controller?.abort(); this.controller = new AbortController(); this.loading = true; message.error = ''
        const controller = this.controller
        try { await this.resumeTask(controller) }
        catch (error) { if (this.isCurrent(controller) && error.code !== 'ERR_CANCELED' && error.name !== 'AbortError') { message.error = error.message; message.errorCode = error.code; message.errorInfo = error.info } }
        finally { if (this.isCurrent(controller)) this.loading = false }
      } else {
        const controller = this.controller
        const source = message.evidence
        this.question = message.role === 'user' ? message.content : [...this.messages.slice(0, this.messages.indexOf(message))].reverse().find(m => m.role === 'user')?.content || ''
        if (source?.dataset_id && source.dataset_id !== this.dataset?.id) await this.chooseDataset(source.dataset_id)
        if (source?.dataset_id === null) { this.dataset = null; this.selectedDatasetId = null }
        if (!this.isCurrent(controller) || (source?.dataset_id && source.dataset_id !== this.dataset?.id)) return
        if (source) {
          const missing = (source.request_options?.inputs || []).filter(input => input.dataset_id !== source.dataset_id && !this.attachedDatasets.some(item => item.id === input.dataset_id))
          if (missing.length) { this.errorMessage = `原分析需要数据集 ${missing.map(input => `#${input.dataset_id}`).join('、')}，请在附件设置中添加后重试。`; return }
          // 历史重新分析固定原消息的输入版本与公开配置；新请求仍由原幂等提交逻辑生成。
          this.runOptions = { depth: 'STANDARD', category: '', profile_ids: [], model_id: null, ...(source.request_options || {}) }
          this.additionalInputIds = (source.request_options?.inputs || []).map(item => item.dataset_id).filter(id => id !== source.dataset_id)
          this.retryVersions = Object.fromEntries((source.request_options?.inputs || []).map(item => [item.dataset_id, item.dataset_version_id]))
          if (source.dataset_id && source.dataset_version_id) this.retryVersions[source.dataset_id] = source.dataset_version_id
        }
        return this.submitQuestion()
      }
    },
  },
}
</script>

<template>
  <AppShell ref="shell" chat :title="sessionTitle || '新对话'">
    <template #actions><el-button text :disabled="initializing" aria-label="查看会话文件" @click="openPreview({ kind: 'workspace' })">文件</el-button></template>
    <div v-if="errorMessage" class="inline-error" role="alert"><span>{{ errorMessage }}</span><el-button text type="primary" @click="initializeWorkspace">重新连接</el-button></div>
    <p v-if="capabilityError" class="capability-warning" role="status">{{ capabilityError }} <button type="button" @click="loadCapabilities(controller)">重试目录</button></p>
    <p v-if="initializing" class="analysis-loading" role="status">正在加载对话…</p>
    <section v-else class="analysis-layout chat-layout" :class="{ 'panel-hidden': !artifactPanelOpen, 'panel-maximized': artifactPanelMaximized, 'workspace-landing': isLanding }" :style="analysisLayoutStyle">
      <div class="conversation-panel" :inert="artifactPanelOpen && compactViewport">
        <div ref="stream" class="conversation-stream" @scroll.passive="onScroll">
          <div ref="streamContent" class="stream-content">
            <el-button v-if="messageCursor" class="load-older-button" text :loading="olderLoading" @click="loadOlderMessages">加载更早的消息</el-button>
            <div v-if="messages.length === 0 && !loading" class="conversation-empty"><h1>想分析什么？</h1></div>
            <ChatMessage v-for="message in messages" :key="message.id" :message="message" :busy="loading" :datasets="datasetChoices" :session-id="sessionId || undefined" @retry="retryMessage" @preview="openPreview" @files="openMessageFiles" @report="reportForMessage" @clarification="useClarificationDataset" />
            <div v-if="loading" class="pending-block">
              <p class="agent-pending" role="status"><span class="status-pulse"></span>{{ runningLabel }}</p>
              <details class="running-details"><summary>查看步骤</summary><AnalysisScope :context="activeResult?.analysis_context" :dataset="dataset" /><AgentSteps :trace="activeTrace" compact /></details>
            </div>
          </div>
        </div>
        <div class="composer-dock">
          <button v-if="!stickToBottom && messages.length" type="button" class="back-to-latest" @click="returnToLatest">↓ 回到最新</button>
          <PromptComposer v-model="question" :busy="loading || choosingDataset" :interruptible="loading" :interrupt-disabled="!canInterrupt" :interrupting="cancelRequested" :uploading="uploadBusy || attachmentBindings > 0" :catalog="catalog" :capabilities="capabilities" :options="runOptions" @interrupt="cancelTask" @option-change="runOptions = { ...runOptions, ...$event }" @submit="submitQuestion" @upload="$refs.uploadQueue.addFiles($event)" @templates="$router.push('/templates')">
            <template #add="{ upload }">
              <el-popover v-model:visible="fileMenuOpen" role="dialog" trigger="click" placement="top-start" :width="200" :disabled="loading || choosingDataset" popper-class="attachment-menu-popper" @after-enter="focusAttachmentMenu" @keydown.esc="closeFilesMenu">
                <template #reference><button ref="addAttachment" type="button" class="attachment-add-button" aria-label="添加附件" :aria-expanded="fileMenuOpen" :disabled="loading || choosingDataset">＋</button></template>
                <div class="attachment-menu"><button type="button" @click="upload(); closeFilesMenu()">上传文件</button><button type="button" @click="openAttachmentSettings">选择已有数据</button><button v-if="capabilities.artifact_references" type="button" @click="openAttachmentSettings">引用已有成果</button><button type="button" @click="openAttachmentSettings">附件设置</button></div>
              </el-popover>
            </template>
            <template #attachments>
              <div v-if="inputDatasets.length" class="session-attachments" aria-label="会话数据附件"><span v-for="item in inputDatasets" :key="item.id"><button type="button" :disabled="loading" :title="item.original_name" @click="openAttachmentSettings">{{ item.original_name }}<small v-if="dataset?.id === item.id"> · v{{ item.current_version_id || '未记录' }}</small></button><button type="button" :disabled="loading || attachmentBindings > 0" :aria-label="`移除附件 ${item.original_name}`" @click="dataset?.id === item.id ? openAttachmentSettings() : removeAttachment(item.id)">{{ dataset?.id === item.id ? '⌄' : '×' }}</button></span></div>
              <div v-if="selectedReferences.length" class="session-attachments"><button v-for="item in selectedReferences" :key="item.id || item.artifact_id" type="button" :title="item.name || item.title" @click="openAttachmentSettings">@ {{ item.name || item.title }}</button></div>
          <UploadQueue ref="uploadQueue" :session-id="Number(sessionId) || undefined" :prepare-session="ensureSession" @document="documentReady" @document-hidden="documentFileId === $event && (documentFileId = null)" :formats="[...(capabilities.file_formats || []), ...(capabilities.document_formats || [])]" :attached-ids="attachedDatasets.map(item => item.id)" :max-files="capabilities.max_files || 10" :max-bytes="capabilities.max_upload_bytes || 20971520" @busy="uploadBusy = $event" @started="startUpload" @ready="attachDataset" @removed="removeAttachment" />
          <div v-if="attachedDocuments.length" class="session-attachments" aria-label="会话文档附件"><el-button v-for="file in attachedDocuments" :key="file.id" @click="documentFileId = file.id; openAttachmentSettings()">{{ file.name }} · 文档</el-button><el-button :disabled="documentPage === 1" @click="documentPage--; loadDocuments()">上一页文档</el-button><el-button :disabled="documentPage * 20 >= documentTotal" @click="documentPage++; loadDocuments()">下一页文档</el-button></div>

            </template>
          </PromptComposer>
          <div v-if="isLanding" class="workspace-suggestions"><button type="button" @click="question = '概览这份数据'">概览数据</button><button type="button" @click="question = '检查缺失值、重复数据和异常值'">检查质量</button><button type="button" @click="question = '根据这份数据生成合适的图表'">生成图表</button></div>
        </div>
      </div>
      <button v-if="artifactPanelOpen" type="button" class="artifact-panel-backdrop" aria-label="关闭预览" @click="toggleArtifactPanel"></button>
      <aside v-if="artifactPanelOpen" class="panel evidence-panel artifact-panel" :role="compactViewport ? 'dialog' : 'complementary'" :aria-modal="compactViewport ? 'true' : undefined" aria-label="结果与文件预览" @keydown="previewKeydown">
        <div v-if="!artifactPanelMaximized" class="artifact-panel-resizer" tabindex="0" role="separator" aria-label="调整工件面板宽度" aria-orientation="vertical" :aria-valuenow="artifactPanelWidth" aria-valuemin="420" aria-valuemax="720" @keydown.left.prevent="artifactPanelWidth = Math.min(720, artifactPanelWidth + 20); savePanelPreference()" @keydown.right.prevent="artifactPanelWidth = Math.max(420, artifactPanelWidth - 20); savePanelPreference()" @pointerdown="startPanelResize" @pointermove="movePanelResize" @pointerup="endPanelResize" @pointercancel="endPanelResize"><span></span></div>

        <header class="evidence-panel-heading"><h2>{{ previewSelection?.kind === 'workspace' ? '会话文件' : previewSelection?.kind === 'files' ? '本轮文件' : previewSelection?.kind === 'chart' ? '图表' : '完整数据' }}</h2><el-button text aria-label="最大化预览" @click="toggleArtifactPanelSize">{{ artifactPanelMaximized ? '还原' : '展开' }}</el-button><button ref="previewClose" type="button" class="preview-close" aria-label="关闭预览" @click="toggleArtifactPanel">×</button></header>
        <p v-if="previewSelection?.evidence" class="caption">分析记录 #{{ previewSelection.evidence.record_id }} · 版本 {{ previewSelection.evidence.dataset_version_id || '未记录' }}</p>
        <p v-if="previewBusy && previewSelection?.kind === 'table'" role="status">正在读取完整数据…</p><p v-if="previewError && previewSelection?.kind === 'table'" role="alert">{{ previewError }}</p>
        <AnalysisResult v-if="['table','chart'].includes(previewSelection?.kind) && !previewBusy" :key="`${previewSelection.evidence.record_id}-${previewSelection.value.artifact_id || previewSelection.value.source_ref}`" :evidence="previewEvidence()" />
        <template v-if="previewSelection?.kind === 'files'">
          <p v-if="previewBusy" role="status">正在读取文件…</p><p v-if="previewError" role="alert">{{ previewError }}</p>
          <p v-if="!previewBusy && !previewError && !previewFiles.length" class="caption">本轮尚无可下载文件，可从“更多”生成报告。</p>
          <div class="message-file-list"><div v-for="file in previewFiles" :key="file.artifact_id || file.id"><button type="button" @click="previewFile(file)">{{ file.file_name || file.name || file.title || `成果 #${file.artifact_id || file.id}` }}</button><span v-if="file.status === 'EXPIRED'">已过期</span><a v-else :href="file.download_url" :download="file.file_name || file.name">下载</a></div></div>
          <ArtifactPreview v-if="previewSelection.filePreview && !previewBusy" :preview="previewSelection.filePreview" :title="previewSelection.file?.file_name || '文件预览'" />
        </template>
        <ArtifactWorkspace v-if="previewSelection?.kind === 'workspace' && sessionId && capabilities.artifact_references" :session-id="sessionId" @report="openReport" @reference="referenceArtifact" />
        <p v-else-if="previewSelection?.kind === 'workspace' && !sessionId" class="caption">添加文件后会显示在这里。</p>
      </aside>
    </section>
    <el-dialog v-model="attachmentSettings" title="附件设置" width="min(520px, calc(100vw - 32px))" class="attachment-settings-dialog">
      <div class="analysis-dataset-picker"><label for="analysis-dataset">当前数据</label><el-select id="analysis-dataset" v-model="selectedDatasetId" filterable remote clearable :remote-method="searchDatasets" placeholder="选择已有数据" :disabled="loading" @change="chooseDataset"><el-option v-for="option in datasetChoices" :key="option.id" :label="option.original_name" :value="option.id" /></el-select></div>
      <el-button v-if="dataset" text @click="$router.push(`/datasets/${dataset.id}`)">查看数据集详情</el-button>
      <div v-if="attachedDatasets.length" class="attachment-settings-list"><div v-for="item in attachedDatasets" :key="item.id"><button type="button" :disabled="loading" @click="chooseDataset(item.id)">{{ item.original_name }}{{ dataset?.id === item.id ? ' · 当前' : '' }}</button><button type="button" :disabled="loading || attachmentBindings > 0 || dataset?.id === item.id" :aria-label="`移除附件 ${item.original_name}`" @click="removeAttachment(item.id)">移除</button></div></div>
      <MentionPicker v-if="capabilities.artifact_references" :items="workspaceArtifacts" :model-value="runOptions.artifact_refs || []" :busy="loading" @update:model-value="runOptions = { ...runOptions, artifact_refs: $event }" />
        <fieldset v-if="capabilities.multi_dataset_execution && dataset && attachedDatasets.some(item => item.id !== dataset.id)" class="analysis-inputs"><legend>同时分析其他附件</legend><label v-for="item in attachedDatasets.filter(item => item.id !== dataset.id)" :key="item.id"><input v-model="additionalInputIds" type="checkbox" :value="item.id" :disabled="loading || choosingDataset" />{{ item.original_name }}</label><p class="caption">所选附件会固定版本参与分析；需要合并数据时，可在数据集页按关联键预览并确认保存。</p></fieldset>
        <SemanticMappingEditor v-if="capabilities.profile_execution && sessionId && dataset" :session-id="Number(sessionId)" :dataset-id="dataset.id" :busy="loading || choosingDataset" />
          <div v-if="documentFileId"><DocumentCandidatePreview :file-id="documentFileId" :session-id="Number(sessionId)" @ready="extractedDataset" /><el-button @click="documentFileId = null">收起附件预览</el-button><p class="caption">收起只关闭预览，文档仍在会话中，刷新可恢复。</p></div>

    </el-dialog>
    <ReportWorkbench v-if="sessionId" :key="`${sessionId}-${selectedReportId || reportSource?.record_id || 'new'}`" v-model="reportDialogVisible" :session-id="sessionId" :report-id="selectedReportId" :source="reportSource" @changed="reportsChanged" />
  </AppShell>
</template>

<style scoped>
.chat-layout { height: 100%; min-height: 0; gap: 0; }
.chat-layout .conversation-panel { position: relative; height: 100%; min-height: 0; max-width: none; width: 100%; margin: 0; border: 0; background: var(--surface); overflow: hidden; }
.chat-layout .conversation-stream { min-height: 0; width: 100%; padding: 36px 32px 8px; overscroll-behavior: contain; }
.stream-content { width: 100%; max-width: 760px; margin: auto; }
.conversation-empty { min-height: 0; padding: 0 0 26px; }
.conversation-empty h1 { margin: 0; font-size: 30px; font-weight: 600; letter-spacing: -.7px; line-height: 1.4; }
.chat-layout.workspace-landing .conversation-panel { justify-content: center; padding-bottom: 10vh; }
.chat-layout.workspace-landing .conversation-stream { flex: 0 0 auto; padding-bottom: 0; }
.composer-dock { position: relative; width: 100%; max-width: 824px; margin: 0 auto; padding: 12px 32px 16px; background: var(--surface); }
.back-to-latest { position: absolute; z-index: 3; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%); border: 1px solid var(--line); border-radius: 20px; background: var(--surface); color: var(--ink); padding: 8px 14px; font-size: 12px; cursor: pointer; box-shadow: 0 3px 12px #2634490c; }
.workspace-suggestions { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 18px; }
.workspace-suggestions button { border: 1px solid var(--line); border-radius: 9px; background: transparent; color: var(--muted); padding: 9px 16px; font-size: 12px; cursor: pointer; }
.workspace-suggestions button:hover { color: var(--ink); background: #f6f7f9; }
.attachment-add-button { display: grid; place-items: center; width: 40px; height: 40px; flex: 0 0 40px; border: 0; border-radius: 8px; color: var(--muted); background: transparent; font-size: 24px; cursor: pointer; }
.attachment-add-button:hover { background: var(--canvas); color: var(--ink); }
.session-attachments { display: flex; flex-wrap: wrap; gap: 6px; min-width: 0; }
.session-attachments > span { display: inline-flex; max-width: 100%; min-width: 0; border: 1px solid var(--line); border-radius: 9px; background: #fafbfc; }
.session-attachments button { min-width: 0; max-width: 100%; padding: 7px 9px; border: 0; border-radius: 7px; background: transparent; font-size: 12px; cursor: pointer; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-attachments small { font-size: 11px; color: var(--muted); }
.pending-block { margin: 0 auto 24px; max-width: 760px; }
.agent-pending { padding: 0; margin: 0 0 6px; font-size: 14px; }
.running-details { padding-top: 4px; font-size: 12px; color: var(--muted); }
.running-details summary { cursor: pointer; }
.chat-layout .artifact-panel { height: 100%; min-height: 0; border-width: 0 0 0 1px; border-radius: 0; padding: 20px; overflow: auto; box-shadow: none; }
.evidence-panel-heading { gap: 8px; margin-bottom: 20px; }
.evidence-panel-heading h2 { flex: 1; font-size: 14px; }
.preview-close { display: grid; place-items: center; width: 36px; height: 36px; border: 0; border-radius: 8px; background: transparent; font-size: 23px; color: var(--muted); cursor: pointer; }
.preview-close:hover { background: var(--canvas); }
.message-file-list { display: grid; gap: 8px; margin: 14px 0; }
.message-file-list > div { display: flex; align-items: center; gap: 12px; }
.message-file-list button { min-width: 0; flex: 1; text-align: left; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); color: var(--ink); overflow-wrap: anywhere; cursor: pointer; }
.message-file-list a { font-size: 12px; color: var(--brand); }
.attachment-settings-list > div { display: flex; justify-content: space-between; gap: 8px; }
.attachment-settings-list button { border: 0; padding: 10px 0; background: transparent; text-align: left; color: var(--muted); overflow-wrap: anywhere; cursor: pointer; }
button:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }
.analysis-inputs { max-width: 100%; }
@media (max-width: 1100px) { .chat-layout .artifact-panel { position: fixed; inset: 68px 0 0 auto; width: min(680px, 90vw); height: calc(100dvh - 68px); z-index: 601; } }
@media (max-width: 600px) { .chat-layout .conversation-stream { padding: 24px 16px 8px; } .composer-dock { padding: 10px 16px max(14px, env(safe-area-inset-bottom)); } .conversation-empty h1 { font-size: 26px; } .chat-layout .artifact-panel { inset: 58px 0 0; width: 100%; height: calc(100dvh - 58px); z-index: 651; } .workspace-suggestions { gap: 8px; } .workspace-suggestions button { padding: 8px 12px; } }
</style>
