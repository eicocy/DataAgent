<script>
import { ElButton } from 'element-plus'
import { datasetApi } from '../api/datasets'
import transformationFlow from '../utils/transformationFlow'
import TransformationPreview from './TransformationPreview.vue'

export default {
  name: 'JoinWorkbench',
  components: { ElButton, TransformationPreview },
  mixins: [transformationFlow],
  data() {
    return {
      flow: 'join', candidates: [], rightId: '', rightVersion: '', versions: [],
      keyPairs: [{ left: '', right: '' }], how: '', relationship: '',
      listLoading: false, listToken: 0, rightToken: 0, page: 1, total: 0,
    }
  },
  computed: {
    payload() {
      // 每一行就是有序键对；不依赖两个多选框各自的 DOM 顺序。
      return {
        dataset_version_id: this.versionId, right_dataset_id: Number(this.rightId),
        right_version_id: Number(this.rightVersion),
        left_on: this.keyPairs.map(pair => pair.left),
        right_on: this.keyPairs.map(pair => pair.right), how: this.how, relationship: this.relationship,
      }
    },
    rightColumns() {
      return this.versions.find(item => item.id === Number(this.rightVersion))?.schema?.columns?.map(item => item.name) || []
    },
    validPairs() {
      return this.keyPairs.length > 0 && this.keyPairs.every(pair => pair.left && pair.right) &&
        new Set(this.keyPairs.map(pair => pair.left)).size === this.keyPairs.length &&
        new Set(this.keyPairs.map(pair => pair.right)).size === this.keyPairs.length
    },
  },
  watch: {
    rightId() { this.loadVersions() },
    rightVersion() { this.keyPairs = [{ left: '', right: '' }] },
    datasetId() { this.loadList() },
  },
  created() { this.loadList() },
  beforeUnmount() { this.listToken++; this.rightToken++ },
  methods: {
    async loadList() {
      const token = ++this.listToken
      this.listLoading = true
      try {
        const value = await datasetApi.list({ status: 'ready', page: this.page, page_size: 20 })
        if (token !== this.listToken) return
        this.candidates = (value.items || []).filter(item => item.id !== this.datasetId)
        this.total = value.total || 0
      } catch (error) {
        if (token === this.listToken) this.error = error.message || '可合并数据集加载失败'
      } finally {
        if (token === this.listToken) this.listLoading = false
      }
    },
    async loadVersions() {
      const token = ++this.rightToken
      this.versions = []
      this.rightVersion = ''
      this.keyPairs = [{ left: '', right: '' }]
      if (!this.rightId) return
      try {
        const value = await datasetApi.versions(this.rightId)
        if (token === this.rightToken) this.versions = value
      } catch (error) {
        if (token === this.rightToken) this.error = error.message || '右表版本加载失败'
      }
    },
    changePage(delta) { this.page += delta; this.loadList() },
    addPair() { if (this.keyPairs.length < 10) this.keyPairs.push({ left: '', right: '' }) },
  },
}
</script>

<template>
  <section aria-label="数据集合并">
    <h3>合并工作台</h3>
    <p>选择拥有的右表和固定版本，声明键关系。键为空或关系不匹配会明确失败；不支持多对多。</p>
    <p v-if="listLoading" role="status">正在查找可合并的数据集…</p>
    <p v-else-if="!candidates.length">
      当前页没有可用右表。请先上传另一个数据集，或翻页查找。
      <ElButton @click="$router.push('/datasets/upload')">上传数据</ElButton><ElButton @click="loadList">刷新列表</ElButton>
    </p>
    <fieldset :disabled="saving">
      <legend>合并配置</legend>
      <label>右表<select v-model="rightId" aria-label="右表"><option value="">请选择数据集</option><option v-for="item in candidates" :key="item.id" :value="item.id">{{ item.original_name }}</option></select></label>
      <label>右表固定版本<select v-model="rightVersion" aria-label="右表固定版本"><option value="">请选择版本</option><option v-for="item in versions" :key="item.id" :value="item.id">版本 {{ item.version_number }}</option></select></label>
      <div v-for="(pair, index) in keyPairs" :key="index" class="join-key-pair">
        <strong>键对 {{ index + 1 }}</strong>
        <label>左表字段<select v-model="pair.left" :aria-label="`键对 ${index + 1} 左表字段`"><option value="">请选择字段</option><option v-for="column in columns" :key="column" :value="column">{{ column }}</option></select></label>
        <span aria-hidden="true">→</span>
        <label>右表字段<select v-model="pair.right" :aria-label="`键对 ${index + 1} 右表字段`"><option value="">请选择字段</option><option v-for="column in rightColumns" :key="column" :value="column">{{ column }}</option></select></label>
        <ElButton :disabled="keyPairs.length === 1" @click="keyPairs.splice(index, 1)">移除键对</ElButton>
      </div>
      <ElButton :disabled="keyPairs.length >= 10" @click="addPair">添加键对</ElButton>
      <label>合并方式<select v-model="how" aria-label="合并方式"><option value="">请选择</option><option value="inner">仅匹配记录</option><option value="left">保留所有左表记录</option></select></label>
      <label>声明键关系<select v-model="relationship" aria-label="声明键关系"><option value="">请选择</option><option value="one_to_one">一对一</option><option value="many_to_one">多对一</option><option value="one_to_many">一对多</option></select></label>
    </fieldset>
    <div aria-label="待预览键配对">
      <p v-for="(pair, index) in keyPairs" :key="index">键对 {{ index + 1 }}：{{ pair.left || '待选择' }} → {{ pair.right || '待选择' }}</p>
      <p v-if="!validPairs">请为每个键对选择左右字段，同一表的键字段不能重复。</p>
    </div>
    <ElButton :disabled="page === 1 || listLoading || saving" @click="changePage(-1)">上一页右表</ElButton>
    <span>第 {{ page }} 页 · 共 {{ total }} 个数据集</span>
    <ElButton :disabled="page * 20 >= total || listLoading || saving" @click="changePage(1)">下一页右表</ElButton>
    <ElButton :disabled="!rightId || !rightVersion || !validPairs || !how || !relationship || saving" :loading="loading" @click="previewChanges">预览合并</ElButton>
    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <TransformationPreview :preview="preview" />
    <ElButton type="primary" :disabled="!preview || loading" :loading="saving" @click="saveVersion">保存为新版本</ElButton>
    <p v-if="notice" role="status">{{ notice }}</p>
  </section>
</template>

<style scoped>
fieldset { display: flex; flex-wrap: wrap; gap: 12px; border: 1px solid var(--line); margin: 12px 0; }
label { display: grid; gap: 6px; }
select { max-width: 220px; padding: 6px; border: 1px solid var(--line); border-radius: var(--radius-sm); }
.join-key-pair { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; flex-basis: 100%; }
</style>
