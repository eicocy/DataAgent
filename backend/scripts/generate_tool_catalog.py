"""Generate the capability directory from actual explicit registrations."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.analysis.catalog import build_registry


def render_catalog():
    canonical=build_registry()
    all_tools=build_registry(include_legacy=True)
    lines=['# Analysis capabilities','','Generated from `app.analysis.catalog.build_registry`; all canonical registrations are exercised by `test_tool_catalog_contracts.py`.','','Available means implemented and covered by automated execution tests. It does not claim real MySQL or live model verification.','','| Tool | Category | Input | Output | Chat | Version | Status |','|---|---|---|---|---|---|---|']
    for tool in canonical.list_tools():
        m=tool.metadata
        lines.append(f'| `{m.name}` | {m.category.value} | `{tool.input_schema.__name__}` | `{tool.output_schema.__name__}` | {"read-only" if m.chat_enabled else "internal only"} | {m.version} | Available |')
    lines+=['','## Compatibility adapters','','Old names and parameters retain their established response fields; SQL additionally requires READ_DATABASE and a configured read-only connection.','','| Adapter | Input | Output | Version |','|---|---|---|---|']
    for tool in all_tools.list_tools():
        if canonical.exists(tool.metadata.name):continue
        lines.append(f'| `{tool.metadata.name}` | `{tool.input_schema.__name__}` | `{tool.output_schema.__name__}` | {tool.metadata.version} |')
    lines+=['','## Current integration and limits','','Plan 1/2 compatibility and Plan 3 owned fixed-input graphs, persistent conversation state, SSE task events and explicit report exports are implemented in their services. Forecast is the registered controlled regular-series baseline tool; it is not automatic machine learning. Join uses only loaded authorized fixed aliases; cleaning publication requires preview and explicit confirmation.','','## Deferred','','Kendall, normality tests, t tests, chi-square and ANOVA are not registered or advertised as Available.','','Dynamic Python and sandbox execution, automatic multi-format reports, a cache platform and machine-learning infrastructure remain reserved future scope.','']
    return '\n'.join(lines)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[2]/'docs'/'analysis-capabilities.md')
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(render_catalog(),encoding='utf-8')
