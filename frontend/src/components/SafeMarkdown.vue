<script>
import MarkdownIt from 'markdown-it'

// 仅解析受控 Markdown；保留默认链接校验，图片语法不产生网络请求。
const parser = new MarkdownIt({ html: false, linkify: false, breaks: true }).disable('image')
export default {
  name: 'SafeMarkdown',
  props: { content: { type: String, default: '' } },
  computed: { rendered() { return parser.render(this.content) } },
}
</script>

<template><div class="markdown-body" v-html="rendered"></div></template>

<style scoped>
.markdown-body { overflow-wrap: anywhere; font-size: 15px; line-height: 1.75; }
.markdown-body :deep(> :first-child) { margin-top: 0; }
.markdown-body :deep(> :last-child) { margin-bottom: 0; }
.markdown-body :deep(p) { margin: 0 0 16px; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { margin: 24px 0 12px; font-size: 18px; line-height: 1.5; font-weight: 600; }
.markdown-body :deep(h1) { font-size: 22px; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: 12px 0; padding-left: 24px; }
.markdown-body :deep(li) { margin: 4px 0; }
.markdown-body :deep(a) { color: var(--brand); text-decoration: underline; }
.markdown-body :deep(pre) { overflow: auto; max-width: 100%; padding: 16px; border-radius: 8px; background: #f5f6f8; font-size: 13px; }
.markdown-body :deep(code) { font-family: var(--font-data), monospace; font-size: .9em; }
.markdown-body :deep(table) { display: block; width: max-content; max-width: 100%; overflow-x: auto; border-collapse: collapse; font-size: 13px; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: 9px 12px; border-bottom: 1px solid var(--line); text-align: left; }
.markdown-body :deep(blockquote) { margin: 16px 0; padding-left: 16px; border-left: 3px solid var(--line); color: var(--muted); }
</style>
