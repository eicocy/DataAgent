"""Report structure varies by audience; every section uses saved calculations."""
from app.reports.schemas import ReportSection

TEMPLATES = {
    'quick': [('executive_summary','分析摘要','insights'),('key_metrics','关键指标','metrics')],
    'detailed': [('executive_summary','执行摘要','insights'),('data_overview','数据范围','overview'),
        ('key_metrics','指标与口径','metrics'),('findings','核心发现与限制','insights'),
        ('visualizations','图表与明细','chart'),('methodology','方法与来源','methods')],
    'executive': [('executive_summary','管理层摘要','insights'),('key_metrics','经营指标','metrics'),
        ('decision_context','变化与决策依据','insights'),('visualizations','业务图表','chart')],
    'technical': [('data_overview','输入版本与范围','overview'),('methodology','工具与参数','methods'),
        ('technical_results','计算结果','metrics'),('technical_limits','验证与限制','insights'),('visualizations','结果图表','chart')],
    'data_quality': [('data_overview','检查范围','overview'),('quality_results','质量规则与结果','metrics'),
        ('quality_limits','清洗建议与口径影响','insights'),('methodology','核对与版本来源','methods')],
    'forecast': [('executive_summary','预测摘要','insights'),('forecast_validation','基线与回测误差','metrics'),
        ('forecast_range','预测范围与不确定性','insights'),('visualizations','预测与区间','chart'),('methodology','时间切分与方法','methods')],
    'general': [('executive_summary','执行摘要','insights'),('data_overview','数据概览','overview'),
        ('key_metrics','关键指标','metrics'),('findings','核心发现','insights'),
        ('visualizations','图表与明细','chart'),('methodology','方法与来源','methods')],
}


def template_sections(spec, evidence_ids, artifacts, sources):
    name = spec.template
    if name == 'auto':
        kinds = {r.get('kind') for source in sources for r in source.get('results', [])}
        name = 'forecast' if 'forecast' in kinds else 'data_quality' if 'quality_score' in kinds else spec.report_type
    name = name if name in TEMPLATES else 'general'
    summary = next((s.get('answer') for s in reversed(sources) if s.get('answer') and s.get('evidence')), None)
    limitations = list(dict.fromkeys(str(item) for source in sources for result in source.get('results', [])
        for item in result.get('limitations', [])))
    if any(source.get('status') == 'partial' for source in sources): limitations.append('分析部分完成；未完成的步骤不构成已验证结论。')
    rows = []
    for identifier,title,kind in TEMPLATES[name]:
        narrative = summary or '当前分析没有可引用的事实结论。' if identifier == 'executive_summary' else None
        if kind == 'insights' and identifier != 'executive_summary':
            narrative = '\n'.join(limitations) or '详见已计算结果与证据；相关性和贡献不能证明因果关系。'
        refs = [aid for aid,item in artifacts.items() if item.get('kind')=='chart' and not item.get('expired')] if kind=='chart' else []
        if kind == 'chart' and not refs: narrative = '当前结果未生成适用图表。'
        rows.append(ReportSection(section_id=identifier,title=title,content_type=kind,narrative=narrative,
            evidence_ids=evidence_ids[:100] if kind in {'insights','methods','metrics'} else [],artifact_refs=refs[:30]))
    rows.append(ReportSection(section_id='evidence_appendix',title='证据附录',content_type='methods',
        evidence_ids=evidence_ids[:100]))
    return rows
