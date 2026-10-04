"""Presentation tables derived only from persisted, validated result values."""
def result_tables(result):
    kind = result.get('kind')
    tables = []
    if result.get('columns') and isinstance(result.get('rows'),list):
        tables.append({'columns':result['columns'],'rows':result['rows'][:100], 'total':result.get('total',len(result['rows']))})
    if kind == 'kpi':
        tables.append({'columns':['指标','值','状态'], 'rows':[{'指标':key,'值':value.get('value'),'状态':value.get('status')} for key,value in result.get('metrics',{}).items()]})
    if kind in {'period_comparison','contribution'}:
        tables.append({'columns':['口径','值','状态'], 'rows':[{'口径':key,'值':result[key].get('value'),'状态':result[key].get('status')} for key in ['current','previous','delta','growth_rate'] if isinstance(result.get(key),dict)]})
        if kind == 'contribution': tables.append({'columns':['dimension','current','previous','delta','contribution_share'],'rows':result.get('groups',[])[:100]})
    if kind == 'forecast':
        tables.append({'columns':['模型','状态','MAE','RMSE','MAPE百分数'], 'rows':[{'模型':c.get('model'),'状态':c.get('status'),
            'MAE':(c.get('metrics') or {}).get('mae'),'RMSE':(c.get('metrics') or {}).get('rmse'),'MAPE百分数':(c.get('metrics') or {}).get('mape')} for c in result.get('candidates',[])]})
        tables.append({'columns':['time','value','lower','upper'],'rows':result.get('points',[])})
    if kind == 'quality_score':
        tables.append({'columns':['质量项目','结果'], 'rows':[{'质量项目':key,'结果':value} for key,value in result.items() if key not in {'kind','dataset_id','dataset_version','source_ref'}]})
    return tables
