"""Business literals are checked against server-bound mapping/metadata evidence."""
MONEY={'revenue','gmv','cost','profit','operating_expense','budget','actual'}
BUSINESS={'kpi_analysis','period_comparison','contribution_analysis'}


def validate_business_arguments(name,args,mappings,version_id,metadata=None):
    mappings=[m for m in mappings or [] if m.get('dataset_version_id')==version_id]
    by_column={m['column']:m for m in mappings}
    metadata=metadata or {}
    if name not in BUSINESS|{'forecast','join_data'}:
        import re
        def strings(value):
            if isinstance(value,str): yield value
            elif isinstance(value,dict):
                for item in value.values(): yield from strings(item)
            elif isinstance(value,list):
                for item in value: yield from strings(item)
        tokens=set(strings(args))
        monetary={column for column,mapping in by_column.items() if mapping.get('concept') in MONEY}
        reduction=bool(tokens & {'sum','avg','mean','median','std','var','min','max'}) or name in {'percentage_share','weighted_average','cumulative_sum','percentage_change','growth_rate','rolling_statistics','time_group_analysis','growth_analysis','rank','top_n','bottom_n'}
        if name in {'group_by_analysis','pivot_table'} and args.get('aggregation','sum') in {'sum','avg','mean','median','std','var','min','max'}:reduction=True
        if (monetary & tokens and reduction) or (name=='sql_query' and re.search(r'\b(sum|avg|min|max)\s*\(',args.get('query',''),re.I) and any(re.search(r'\b'+re.escape(column)+r'\b',args.get('query',''),re.I) for column in monetary)):
            raise ValueError('BUSINESS_EXACT_TOOL_REQUIRED')
    if name=='kpi_analysis':
        fields=list(args.get('metrics',{}).values())
        for concept,column in args.get('metrics',{}).items():
            mapping=by_column.get(column)
            if mapping and mapping.get('source') in {'confirmed','user'} and mapping['concept']!=concept:
                # actual/revenue can share a monetary measurement, but quantity
                # must never become money because a plan declares it so.
                if mapping['concept'] not in MONEY: raise ValueError('BUSINESS_METRIC_CONFLICT')
        money=bool(fields)
    elif name in {'period_comparison','contribution_analysis'}:
        fields=[args.get('value_column')];money=args.get('value_kind','money')=='money'
        mapped=by_column.get(fields[0])
        if mapped and mapped.get('source') in {'confirmed','user'}:
            if (money and mapped['concept']=='quantity') or (not money and mapped['concept'] in MONEY):
                raise ValueError('BUSINESS_METRIC_CONFLICT')
    elif name=='forecast':
        fields=[args.get('target_column')];money=by_column.get(fields[0],{}).get('concept') in MONEY
        if not money: return {}
    else: return {}
    if not fields: return {}
    resolved={}
    for label in (('currency','unit') if money else ('unit',)):
        confirmed=[by_column.get(column,{}) for column in fields]
        trusted={m[label] for m in confirmed if m.get('source') in {'confirmed','user'} and m.get(label)}
        if len(trusted)>1: raise ValueError('BUSINESS_METADATA_CONFLICT')
        column=args.get(label+'_column') or metadata.get(label,{}).get('column')
        info=metadata.get(label,{})
        if column:
            if column not in info.get('columns',[info.get('column')]) or info.get('status')!='valid':
                raise ValueError('BUSINESS_METADATA_INVALID')
            if trusted and info['value'] not in trusted: raise ValueError('BUSINESS_METADATA_CONFLICT')
            trusted={info['value']}
        elif len(confirmed)!=sum(m.get('source') in {'confirmed','user'} and bool(m.get(label)) for m in confirmed):
            raise ValueError('BUSINESS_METADATA_REQUIRED')
        if not trusted: raise ValueError('BUSINESS_METADATA_REQUIRED')
        value=next(iter(trusted))
        if args.get(label) is not None and args[label]!=value: raise ValueError('BUSINESS_METADATA_CONFLICT')
        resolved[label]=value
        if name in BUSINESS:
            args[label]=value
            if column: args[label+'_column']=column
    return resolved


def joined_mappings(left,right,left_columns,right_columns,args,version_id):
    shared={l for l,r in zip(args['left_on'],args['right_on']) if l==r}
    overlap=(set(left_columns)&set(right_columns))-shared
    result=[]
    for mappings,suffix in [(left,'_left'),(right,'_right')]:
        for mapping in mappings:
            column=mapping['column']
            result.append(dict(mapping,column=column+suffix if column in overlap else column,dataset_version_id=version_id))
    return result


def metadata_evidence(frame):
    """Recognized metadata column names, actual whole-series homogeneity only."""
    aliases={'currency':{'currency','currency_code','币种'},'unit':{'unit','amount_unit','单位'}}
    result={}
    def original_name(column):
        name=str(column).lower()
        while name.endswith(('_left','_right')):
            name=name.rsplit('_',1)[0]
        return name
    labels=dict(zip(frame.columns,frame.attrs.get('original_columns',list(frame.columns))))
    for label,names in aliases.items():
        found=[column for column in frame if original_name(column) in names or original_name(labels.get(column,column)) in names]
        if not found:continue
        # Conservatively require all recognized source metadata to agree after
        # Join suffixing. A literal mapping cannot hide any retained mixed source.
        series=pd_concat_columns(frame,found)
        valid=not series.empty and not series.isna().any() and series.map(lambda v:isinstance(v,str) and bool(v.strip())).all() and series.nunique()==1
        result[label]={'column':found[0],'columns':found,'status':'valid' if valid else 'mixed_or_invalid','value':series.iloc[0] if valid else None}
    return result


def pd_concat_columns(frame,columns):
    import pandas as pd
    return pd.concat([frame[column] for column in columns],ignore_index=True)
