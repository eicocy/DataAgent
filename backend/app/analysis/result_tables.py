"""Expose typed verified results as display tables without arithmetic."""
def result_table(data,source_ref,limit=100):
    kind=data.get('kind')
    if kind=='kpi':
        columns=['metric','value','status','explanation']
        rows=[dict(metric=name,**value) for name,value in data['metrics'].items()]
    elif kind=='period_comparison':
        columns=['metric','value','status','explanation']
        rows=[dict(metric=name,**data[name]) for name in ('current','previous','delta','growth_rate')]
    elif kind=='contribution':
        columns=['dimension','current','previous','delta','contribution_share'];rows=data['groups']
    elif kind=='forecast':
        columns=['time','value','lower','upper'];rows=data['points']
    elif kind=='quality_score':
        columns=['issue','column','count','penalty','severity','suggestion'];rows=[{column:f.get(column) for column in columns} for f in data['findings']]
    else:return None
    metadata={key:data[key] for key in ('kind','currency','unit','unit_status','limitations','current_range','previous_range','value_kind','score','rule_version') if key in data}
    return dict(metadata,columns=columns,rows=rows[:limit],row_count=len(rows),truncated=len(rows)>limit,source_ref=source_ref)
