import sqlglot

def validate_readonly_query(query: str, dataset_id: int, allowed_columns: set[str], max_rows: int) -> str:
    try:
        statements = sqlglot.parse(query, read="mysql")
    except sqlglot.errors.ParseError as exc:
        raise ValueError("invalid SQL syntax") from exc
    if len(statements) != 1 or not isinstance(statements[0], sqlglot.exp.Select):
        raise ValueError("only a single SELECT statement is allowed")
    tree = statements[0]
    if any(node.comments for node in tree.walk()) or tree.find(sqlglot.exp.Hint):
        raise ValueError('SQL comments and hints are not allowed')
    if any(tree.find(kind) for kind in (sqlglot.exp.Join, sqlglot.exp.Subquery, sqlglot.exp.CTE, sqlglot.exp.Union, sqlglot.exp.Parameter, sqlglot.exp.Window)) or len(list(tree.find_all(sqlglot.exp.Select))) != 1:
        raise ValueError('only a single-table SELECT without nested queries is allowed')
    if tree.find(sqlglot.exp.Into) or tree.find(sqlglot.exp.Lock):
        raise ValueError("only a read-only SELECT is allowed")
    allowed_functions = {'SUM', 'AVG', 'MIN', 'MAX', 'COUNT', 'ROUND', 'COALESCE', 'NULLIF', 'DATE', 'DATE_FORMAT', 'TIME_TO_STR', 'YEAR', 'MONTH', 'CAST'}
    for function in tree.find_all(sqlglot.exp.Func):
        name = function.name.upper() if isinstance(function, sqlglot.exp.Anonymous) else function.sql_name().upper()
        if name not in allowed_functions:
            raise ValueError("SQL contains a disallowed function")
    expected_table = f"dataset_{int(dataset_id)}"
    tables = list(tree.find_all(sqlglot.exp.Table))
    if len(tables) != 1 or any(table.name.lower() != expected_table.lower() or table.db or table.catalog for table in tables):
        raise ValueError("SQL may access only the current dataset table")
    output_aliases = {
        projection.alias.lower()
        for projection in tree.expressions
        if isinstance(projection, sqlglot.exp.Alias)
    }
    for column in tree.find_all(sqlglot.exp.Column):
        if column.name != "*" and column.name not in allowed_columns and column.name.lower() not in output_aliases:
            raise ValueError(f"SQL field is not available in the current dataset: {column.name}")
        if column.table and column.table.lower() not in {expected_table.lower(), tables[0].alias_or_name.lower()}:
            raise ValueError('SQL table qualifier is not authorized')
    expanded = []
    for projection in tree.expressions:
        if isinstance(projection, sqlglot.exp.Star) or (isinstance(projection, sqlglot.exp.Column) and projection.name == '*'):
            expanded.extend(sqlglot.exp.column(name, quoted=True) for name in sorted(allowed_columns))
        else:
            expanded.append(projection)
    tree.set('expressions', expanded)
    limit_node = tree.args.get("limit")
    if limit_node:
        value = limit_node.expression
        if not isinstance(value, sqlglot.exp.Literal) or not value.is_int:
            raise ValueError("LIMIT must be a positive integer")
        tree_limit = int(value.this)
        if tree_limit < 1:
            raise ValueError("LIMIT must be a positive integer")
        if tree_limit > max_rows:
            limit_node.set("expression", sqlglot.exp.Literal.number(max_rows))
    else:
        tree.set("limit", sqlglot.exp.Limit(expression=sqlglot.exp.Literal.number(max_rows)))
    return tree.sql(dialect="mysql")
