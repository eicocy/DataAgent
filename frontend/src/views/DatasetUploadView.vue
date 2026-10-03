<script>
import { mapState, mapActions } from 'pinia'
import { ArrowLeft, DocumentAdd, UploadFilled } from '@element-plus/icons-vue'

import AppShell from '../components/AppShell.vue'
import { datasetApi } from '../api/datasets'
import { useDatasetStore } from '../stores/datasets'

export default {
  name: 'DatasetUploadView',
  components: { AppShell, ArrowLeft, DocumentAdd, UploadFilled },
  data() { return { selectedFile: null, sheetNames: [], selectedSheet: '', inspectingSheets: false, uploading: false, uploadPercent: 0, errorMessage: '', controller: null, inspectionController: null, dragging: false } },
  computed: { ...mapState(useDatasetStore, ['uploadStatus']) },
  beforeUnmount() { this.controller?.abort(); this.inspectionController?.abort(); this.inspectionController = null },
  methods: {
    ...mapActions(useDatasetStore, ['upload']),
    async chooseFile(file) {
      if (this.uploading) return
      this.inspectionController?.abort()
      const controller = new AbortController()
      this.inspectionController = controller
      this.inspectingSheets = false
      this.errorMessage = ''
      if (!file) return
      if (!/\.(csv|tsv|json|parquet|xls|xlsx)$/i.test(file.name)) { this.errorMessage = '支持 CSV、TSV、JSON、XLS、XLSX 和 Parquet 文件'; return }
      if (file.size > 20 * 1024 * 1024) { this.errorMessage = '文件不能超过 20 MB'; return }
      this.selectedFile = file
      this.sheetNames = []
      this.selectedSheet = ''
      if (/\.xlsx?$/i.test(file.name)) {
        this.inspectingSheets = true
        try {
          // 上传前先读取工作表名称，用户选择后再随原文件一同提交。
          const result = await datasetApi.inspectSheets(file, { signal: controller.signal })
          if (this.inspectionController !== controller || controller.signal.aborted) return
          this.sheetNames = result.sheets || []
          this.selectedSheet = result.default || this.sheetNames[0] || ''
        } catch (error) {
          if (this.inspectionController !== controller || controller.signal.aborted) return
          this.errorMessage = error.message || '无法读取 Excel 工作表'
          this.selectedFile = null
        } finally { if (this.inspectionController === controller) this.inspectingSheets = false }
      }
    },
    handleInput(event) { this.chooseFile(event.target.files?.[0]); event.target.value = '' },
    handleDrop(event) { this.dragging = false; this.chooseFile(event.dataTransfer.files?.[0]) },
    async submit() {
      if (!this.selectedFile || this.uploading || this.inspectingSheets) return
      this.errorMessage = ''; this.uploading = true; this.uploadPercent = 0
      this.controller = new AbortController()
      try {
        const dataset = await this.upload(this.selectedFile, { signal: this.controller.signal, sheetName: this.selectedSheet, onUploadProgress: (event) => { if (event.total) this.uploadPercent = Math.round((event.loaded / event.total) * 100) } })
        this.$router.replace({ name: 'dataset-detail', params: { datasetId: dataset.id } })
      } catch (error) {
        if (error.name !== 'AbortError') this.errorMessage = error.message || '上传失败，请重试'
      } finally { this.uploading = false; this.controller = null }
    },
    formatSize(bytes) { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB` },
  },
}
</script>

<template>
  <AppShell>
    <section class="page-heading upload-heading"><div><el-button text class="back-link" @click="$router.push('/datasets')"><el-icon><ArrowLeft /></el-icon>返回数据集</el-button><p class="eyebrow">添加数据</p><h1>上传数据集</h1><p class="page-intro">选择表格或记录文件，DataLens 会为你整理字段和数据预览。</p></div></section>
    <section class="upload-layout">
      <article class="panel upload-main">
        <div class="panel-title"><h2>选择文件</h2><span>单文件最大 20 MB</span></div>
        <input id="dataset-file" ref="fileInput" class="visually-hidden" type="file" aria-label="选择 CSV、TSV、JSON、XLS、XLSX 或 Parquet 文件" accept=".csv,.tsv,.json,.parquet,.xls,.xlsx" @change="handleInput" />
        <div class="drop-zone" :class="{ 'is-dragging': dragging, 'has-file': selectedFile }" role="button" tabindex="0" aria-controls="dataset-file" @click="$refs.fileInput.click()" @keydown.enter.prevent="$refs.fileInput.click()" @keydown.space.prevent="$refs.fileInput.click()" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="handleDrop">
          <span class="drop-icon"><el-icon><UploadFilled v-if="!selectedFile" /><DocumentAdd v-else /></el-icon></span><strong>{{ selectedFile ? selectedFile.name : '拖放文件到这里，或点击选择' }}</strong><small>{{ selectedFile ? formatSize(selectedFile.size) : '支持 CSV、TSV、JSON、XLS、XLSX、Parquet' }}</small><span v-if="!selectedFile" class="browse-button">浏览文件</span>
        </div>
        <div v-if="sheetNames.length" class="sheet-picker"><label for="dataset-sheet">选择工作表</label><el-select id="dataset-sheet" v-model="selectedSheet" :disabled="uploading || inspectingSheets"><el-option v-for="sheet in sheetNames" :key="sheet" :label="sheet" :value="sheet" /></el-select><small>默认选择第一个非空工作表</small></div>
        <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
        <div v-if="uploading" class="upload-progress" aria-live="polite"><div class="progress-top"><strong>{{ uploadStatus === 'parsing' ? '正在解析数据' : '正在上传文件' }}</strong><span>{{ uploadStatus === 'parsing' ? '请稍候' : `${uploadPercent}%` }}</span></div><el-progress :percentage="uploadStatus === 'parsing' ? 100 : uploadPercent" :indeterminate="uploadStatus === 'parsing'" :show-text="false" /><p>{{ uploadStatus === 'parsing' ? '识别字段、检查数据质量并准备预览。' : '文件将通过安全连接传输。' }}</p></div>
        <div class="upload-actions"><el-button @click="$router.push('/datasets')">取消</el-button><el-button type="primary" :disabled="!selectedFile" :loading="uploading" @click="submit">上传并解析</el-button></div>
      </article>
      <aside class="panel upload-guide"><div class="guide-icon"><el-icon><DocumentAdd /></el-icon></div><h2>上传后会发生什么？</h2><ol><li><span>01</span><p><strong>检查文件</strong><small>验证格式与文件大小</small></p></li><li><span>02</span><p><strong>识别字段</strong><small>整理列名、类型和缺失值</small></p></li><li><span>03</span><p><strong>准备预览</strong><small>生成有限行数据预览</small></p></li></ol><p class="guide-note">支持 XLS、XLSX 工作表选择；嵌套 JSON 暂不支持。分析仅使用授权字段、Profile 和计算结果。</p></aside>
    </section>
  </AppShell>
</template>
