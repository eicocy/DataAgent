"""Export an audited plan as a local reproduction script, never execute it here."""
import json


class CodeExporter:
    def __init__(self,format): self.format = format
    def export(self,document,options):
        return export_plan(options.source_plan,self.format,document.title,options.input_snapshots)


def export_plan(plan,format,title,inputs=None):
    from app.reports.exporters import ExportFile
    from app.artifacts.storage import LocalArtifactStorage
    from app.analysis.catalog import build_registry
    inputs = inputs or []
    steps = [step for step in plan.get('steps',[]) if step.get('status')=='COMPLETED']
    if not steps: raise ValueError('REPORT_CODE_PLAN_UNAVAILABLE')
    if format == 'sql':
        from app.analysis.sql_safety import validate_readonly_query
        statements = []
        for step in steps:
            if step.get('tool_name') != 'sql_query': continue
            alias = step.get('input_alias','primary')
            binding = next((i for i in inputs if i.get('alias','primary')==alias),None)
            if not binding: raise ValueError('SQL_EXPORT_VERSION_UNAVAILABLE')
            args = step.get('arguments') or {}
            query = validate_readonly_query(args.get('query',''),binding['dataset_id'],
                {c['name'] for c in binding.get('schema',{}).get('columns',[])},1000)
            statements.append(f"-- Fixed dataset {binding['dataset_id']} version {binding['dataset_version_id']}\n{query};")
        if not statements: raise ValueError('SQL_EXPORT_NO_VERIFIED_SELECT')
        return [ExportFile(LocalArtifactStorage.safe_file_name(title,'sql'),'application/sql','\n\n'.join(statements).encode())]
    if format != 'python': raise ValueError('REPORT_FORMAT_UNSUPPORTED')
    registry = build_registry(include_legacy=True)
    rejected = []
    for step in steps:
        tool = registry.get(step['tool_name'])
        if tool.metadata.modifies_dataset or step['tool_name'] in {'sql_query'} or step['tool_name'] in {
            'get_dataset_info','preview_data','aggregate_data','group_by_analysis','sort_data',
            'filter_data','descriptive_stats','missing_values','duplicates','correlation_analysis','value_counts'}:
            rejected.append(step['step_id'])
    # The export is honest about operations requiring the trusted app adapter.
    bindings = [{**next((snapshot for snapshot in inputs if snapshot['dataset_id']==item['dataset_id'] and snapshot['dataset_version_id']==item['dataset_version_id']),{}),**item}
        for item in plan.get('inputs') or inputs]
    payload = {'inputs':bindings, 'semantic_snapshot':plan.get('semantic_snapshot',[]), 'steps':steps, 'unsupported_steps':rejected,
        'dataset_id':plan.get('dataset_id'), 'dataset_version_id':plan.get('dataset_version_id')}
    encoded = json.dumps(payload,ensure_ascii=False,allow_nan=False)
    script = '''"""Reproduce a saved DataAgent plan against explicitly supplied fixed CSV snapshots.
Run from backend with its requirements installed; no network/model/DB credentials.
"""
import argparse
import json
from pathlib import Path
from decimal import Decimal
import pandas as pd
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.analysis.engine import AnalysisEngine, ExecutionContext
from app.analysis.models import ToolExecutionRequest

PLAN = json.loads(PLAN_LITERAL)

def resolve(value, results):
    if isinstance(value, dict):
        if set(value) == {'$ref', 'field'}: return results[value['$ref']][value['field']]
        return {key: resolve(item, results) for key, item in value.items()}
    if isinstance(value, list): return [resolve(item, results) for item in value]
    return value

def main():
    parser = argparse.ArgumentParser(description='Replay a fixed DataAgent plan locally')
    parser.add_argument('--input', action='append', required=True, metavar='ALIAS=CSV')
    parser.add_argument('--output', default='reproduced-results.json')
    args = parser.parse_args()
    if PLAN['unsupported_steps']:
        raise SystemExit('These steps require the original application adapter: ' + ', '.join(PLAN['unsupported_steps']))
    paths = dict(item.split('=', 1) for item in args.input)
    bindings = PLAN['inputs'] or [{'alias':'primary','dataset_id':PLAN['dataset_id'],'dataset_version_id':PLAN['dataset_version_id']}]
    if set(paths) != {item['alias'] for item in bindings}: raise SystemExit('Supply every fixed input alias exactly once')
    registry = build_registry(include_legacy=True)
    engine = AnalysisEngine(registry)
    def load_input(item):
        columns = item.get('schema', {}).get('columns', [])
        if not columns: return pd.read_csv(paths[item['alias']])
        frame = pd.read_csv(paths[item['alias']], dtype='string')
        if list(frame.columns) != [c['name'] for c in columns]: raise SystemExit('Input columns differ from the saved snapshot')
        for column in columns:
            name, kind, dtype = column['name'], column.get('storage_type'), column.get('dtype', 'object')
            if kind == 'decimal' and dtype == 'object': frame[name] = frame[name].map(lambda v: None if pd.isna(v) else Decimal(v))
            elif kind in {'date','datetime'} or 'datetime' in dtype: frame[name] = pd.to_datetime(frame[name], errors='raise')
            elif kind == 'boolean' or dtype in {'bool','boolean'}:
                values = {'True':True,'False':False,'true':True,'false':False}
                if not frame[name].dropna().isin(values).all(): raise SystemExit('Invalid boolean in fixed input')
                frame[name] = frame[name].map(values).astype('boolean')
            elif kind == 'integer' or dtype.lower().startswith(('int','uint')): frame[name] = frame[name].astype('Int64')
            elif kind == 'decimal' or dtype.startswith('float'): frame[name] = pd.to_numeric(frame[name], errors='raise')
        frame.attrs['original_columns'] = [c.get('original_name', c['name']) for c in columns]
        return frame
    datasets = {item['alias']: DatasetContext.from_frame(load_input(item),
        dataset_id=item['dataset_id'], dataset_version=item['dataset_version_id'], registry=registry) for item in bindings}
    frames, results = {}, {}
    for step in PLAN['steps']:
        if any(dep not in results for dep in step.get('depends_on', [])): raise SystemExit('A required source is unavailable')
        alias = step.get('input_alias', bindings[0]['alias'])
        base = datasets[alias]
        source_ref = step.get('source_ref', 'dataset')
        frame = base.frame if source_ref == 'dataset' else frames[source_ref]
        from app.semantic.business_validation import validate_business_arguments, metadata_evidence
        parameters = resolve(step.get('arguments', {}), results)
        monetary = validate_business_arguments(step['tool_name'], parameters, PLAN['semantic_snapshot'], base.dataset_version, metadata_evidence(frame))
        context = DatasetContext.from_frame(frame.copy(deep=True), dataset_id=base.dataset_id,
            dataset_version=base.dataset_version, source_ref=source_ref, registry=registry,
            related_inputs={key: value for key,value in datasets.items() if key != alias}, monetary_metadata=monetary)
        captured = []
        result = engine.execute(ToolExecutionRequest(tool_name=step['tool_name'],
            dataset_id=base.dataset_id, dataset_version=base.dataset_version,
            parameters=parameters, request_id=step['step_id']),
            ExecutionContext(user_id=1, dataset=context, capture_frame=captured.append))
        results[step['step_id']] = result.data.model_dump(mode='json')
        if captured and captured[0] is not None: frames[step['step_id']] = captured[0]
    Path(args.output).write_text(json.dumps(results, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')

if __name__ == '__main__': main()
'''.replace('PLAN_LITERAL',repr(encoded))
    readme = '依赖与重现说明\n\n使用本版本 DataAgent backend 源码和 requirements.txt，在本地运行导出脚本。\n'
    readme += '输入必须为报告所记录的固定版本完整 CSV 明细；参数 --input primary=path.csv，其他输入按 alias 补齐。\n'
    readme += '输出为计算结果 JSON；不调用模型，不含凭据，不在服务器执行。原始解析精度和预测不确定性限制继续适用。\n'
    if rejected: readme += '受限步骤：'+', '.join(rejected)+'；脚本会明确停止，请在原应用读取其已保存结果。\n'
    return [ExportFile(LocalArtifactStorage.safe_file_name(title,'py'),'text/x-python',script.encode()),
        ExportFile(LocalArtifactStorage.safe_file_name(title+'_依赖说明','md'),'text/markdown; charset=utf-8',readme.encode())]
