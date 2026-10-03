"""Strategy routing with explicit capability and data ambiguity handling."""
import re
from pydantic import BaseModel, Field


class ProfileRoute(BaseModel):
    profile_ids: list[str] = Field(default_factory=list, max_length=3)
    category: str = 'general'
    confidence: float = Field(default=0, ge=0, le=1)
    reason: str = ''
    missing_requirements: list[str] = Field(default_factory=list)
    needs_clarification: bool = False


class AnalysisTemplateRouter:
    def __init__(self, catalog):
        self.catalog = {p['id']: p for p in catalog}

    def route(self, question, explicit_ids=None, semantics=None, category=None):
        text = re.sub(r'不是[^，,。；;]+', '', question.lower())
        ids = list(explicit_ids or [])
        confidence = 1.0 if ids else .8
        if not ids:
            if category == 'custom':
                ids.append('custom-question')
            if re.search(r'预测|forecast|未来|下季度', text):
                ids.append('forecast-sales')
            if re.search(r'销售|sales|卖|销量', text):
                ids.insert(0, 'sales-decline' if re.search(r'下降|下滑|减少', text) else 'sales-ranking' if re.search(r'最好|排名|排行|top|最多', text) else 'sales-growth' if re.search(r'增长', text) else 'sales-overview')
            if re.search(r'利润|财务|成本|profit|finance', text):
                ids.append('finance-profit' if '利润' in text or 'profit' in text else 'finance-overview')
            if ids and re.search(r'质量|缺失|重复', text):
                ids.append('general-quality')
            if not ids:
                ids = ['general-quality' if re.search(r'质量|问题|缺失|重复|错误', text) else 'general-clean' if '清洗' in text else 'general-eda' if re.search(r'eda|相关|分布|统计', text) else 'general-explore']
                if not re.search(r'分析|数据|表|探索|统计|检查|看看', text):
                    confidence = .5
        missing = []
        if len(ids) > 3:
            missing.append('一次最多组合三个分析模板，请缩小分析范围。')
        ids = list(dict.fromkeys(ids))[:3]
        for key in ids:
            profile = self.catalog.get(key)
            if not profile or profile['availability'] == 'planned':
                missing.append(f"{profile['name'] if profile else key} 的必要工具尚未开放。")
            if category and profile and profile['category'] not in {category, 'general'}:
                missing.append('分析方向与识别到的任务不一致，请选择对应模板或使用自动方向。')
        if any(self.catalog.get(key, {}).get('category') in {'sales', 'finance'} for key in ids):
            ambiguous = [s['column'] for s in semantics or [] if s.get('concept') == 'ambiguous_sales' and s.get('source') != 'user']
            if ambiguous:
                missing.append(f"请确认 {', '.join(ambiguous)} 表示金额还是销量。")
            if semantics is not None:
                metrics = {s.get('concept') for s in semantics if s.get('role') == 'metric' and s.get('concept') != 'ambiguous_sales'}
                if not metrics:
                    missing.append('未识别到明确业务指标，请确认要分析的金额、销量或其他字段。')
                expected = 'revenue' if re.search(r'销售额|销售金额|营业额|revenue', text) else 'quantity' if re.search(r'销量|销售数量|quantity', text) else None
                if expected and expected not in metrics:
                    missing.append('问题中的指标尚未映射到字段，请确认字段含义。')
                if expected is None and len(metrics & {'revenue', 'quantity', 'gmv'}) > 1:
                    missing.append('同时存在金额和销量指标，请说明本次排名或比较采用哪个指标。')
                if re.search(r'今年|同比|环比|趋势|增长|下降|下滑', text) and not any(s.get('concept') == 'time' for s in semantics):
                    missing.append('未识别到时间字段，无法确定比较区间，请确认时间字段。')
        return ProfileRoute(profile_ids=ids, category=self.catalog.get(ids[0], {}).get('category', 'general'), confidence=confidence,
            reason='用户显式选择' if explicit_ids else '根据问题关键词匹配可复用分析策略', missing_requirements=missing,
            needs_clarification=confidence < .75 or bool(missing))
