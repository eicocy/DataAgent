"""Conservative syntax surface; container isolation remains the security boundary."""
import ast

MAX_CODE_BYTES = 32 * 1024
MODULES = {'pandas', 'numpy', 'math', 'statistics', 'decimal', 'matplotlib.pyplot'}
BUILTINS = {'abs','all','any','bool','dict','enumerate','float','int','len','list','max','min','print','range','round','set','sorted','str','sum','tuple','zip','Exception','ValueError'}
# Positive list: no file readers/writers, reflection, dynamic import, pandas
# query/eval, option/backend selection, object internals or subprocess APIs.
ATTRIBUTES = set('''DataFrame Series Index array arange linspace zeros ones full concatenate stack column_stack reshape flatten ravel astype copy tolist to_list to_dict to_frame
columns index values shape size ndim dtype dtypes empty loc iloc T name
abs all any sum mean median std var min max count quantile describe corr cov cumsum cumprod diff pct_change
groupby agg aggregate apply map transform pivot pivot_table melt stack unstack reset_index set_index rename drop dropna fillna isna notna isin duplicated drop_duplicates sort_values sort_index head tail sample select_dtypes value_counts nunique unique
rolling expanding ewm resample shift clip where mask replace rank round assign insert pop
sqrt log log10 exp sin cos tan floor ceil isnan isfinite isinf nan nanmean nanmedian nanstd nanvar nansum nanmin nanmax percentile average dot linalg norm svd lstsq polyfit polyval
Decimal sqrt as_tuple is_finite
items keys get append extend update add join lower upper strip split startswith endswith
subplots figure plot scatter bar hist boxplot imshow title xlabel ylabel legend grid tight_layout set_title set_xlabel set_ylabel set_xticks set_xticklabels axhline axvline fill_between text
to_datetime to_numeric dt year month day date weekday days total_seconds str contains len
pi e inf nan'''.split())
FORBIDDEN_NAMES = {'eval','exec','compile','open','input','globals','locals','vars','dir','getattr','setattr','delattr','type','object','super','help','breakpoint','exit','quit','memoryview','__builtins__'}
DISPATCH_METHODS = {'apply','agg','aggregate','map','transform'}
SAFE_REDUCTIONS = {'sum','mean','median','std','var','min','max','count','size','nunique','first','last','prod','all','any'}


def safe_dispatch(node):
    if isinstance(node, ast.Lambda): return True
    if isinstance(node, ast.Constant): return isinstance(node.value,str) and node.value in SAFE_REDUCTIONS
    if isinstance(node, (ast.List,ast.Tuple)): return bool(node.elts) and all(safe_dispatch(item) for item in node.elts)
    if isinstance(node, ast.Dict): return bool(node.values) and all(safe_dispatch(item) for item in node.values)
    return False


class SandboxError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_code(code):
    if not isinstance(code, str) or not code.strip() or len(code.encode('utf-8')) > MAX_CODE_BYTES:
        raise SandboxError('SANDBOX_CODE_LIMIT')
    try:
        tree = ast.parse(code)
    except (SyntaxError, RecursionError, ValueError):
        raise SandboxError('SANDBOX_SYNTAX_INVALID') from None
    nodes = list(ast.walk(tree))
    parents = {child:parent for parent in nodes for child in ast.iter_child_nodes(parent)}
    if len(nodes) > 5000:
        raise SandboxError('SANDBOX_CODE_LIMIT')
    for node in nodes:
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.With, ast.AsyncWith, ast.Global, ast.Nonlocal)):
            raise SandboxError('SANDBOX_SYNTAX_DENIED')
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.name.startswith('_')):
            raise SandboxError('SANDBOX_SYNTAX_DENIED')
        if isinstance(node, ast.Name) and (node.id.startswith('_') or node.id in FORBIDDEN_NAMES):
            raise SandboxError('SANDBOX_NAME_DENIED')
        if isinstance(node, ast.Attribute) and node.attr not in ATTRIBUTES:
            raise SandboxError('SANDBOX_ATTRIBUTE_DENIED')
        if isinstance(node, ast.Attribute) and node.attr in DISPATCH_METHODS:
            call = parents.get(node)
            if not isinstance(call,ast.Call) or call.func is not node:
                raise SandboxError('SANDBOX_DISPATCH_DENIED')
            function = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg in {'func','function'}),None)
            if not safe_dispatch(function): raise SandboxError('SANDBOX_DISPATCH_DENIED')
        if isinstance(node, ast.keyword) and node.arg in {'engine','backend','storage_options','path','path_or_buf','buf'}:
            raise SandboxError('SANDBOX_IO_DENIED')
        if isinstance(node, ast.Import):
            if any(item.name not in MODULES or (item.asname or '').startswith('_') for item in node.names):
                raise SandboxError('SANDBOX_IMPORT_DENIED')
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in MODULES or any(item.name not in ATTRIBUTES or (item.asname or '').startswith('_') for item in node.names):
                raise SandboxError('SANDBOX_IMPORT_DENIED')
    return tree
