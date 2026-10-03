# Tool development

Phase 2 adds a framework-independent analysis package in `backend/app/analysis/`. Domain tools receive a fixed `DatasetContext` and a Pydantic input, returning `ToolOutput` with a typed data model and optional full DataFrame. They do not receive HTTP requests, user-provided paths, SQL connections or model clients. The SQL compatibility adapter is the established infrastructure boundary, using only its authorized read-only connection.

## Execution path

`Authorized DatasetVersion → DatasetContext → Registry input/permission validation → computation → typed output → ResultValidator → artifacts/execution record → caller`.

`AnalysisEngine.execute(request, ExecutionContext)` performs deterministic execution, deadlines and lease checks. User identity, grants, publisher and persistence callbacks come from the trusted context. `ToolExecutionRequest.parameters` cannot grant permissions. A transformation without a trusted publisher is rejected by Engine. `ToolExecutionService` is an internal Python service; no generic public execution route was added.

DatasetContext contains the fixed dataset/version, Schema/Profile, full DataFrame, source reference and budgets. Published versions reuse their stored profiles. DatasetTools caches one context per source in a workflow. Downstream steps use full validated frames, retaining the original version provenance; clipped previews never become computation inputs. Read tools do not mutate the input. Cleaning works on independent data and requires READ_DATA plus TRANSFORM_DATA. Cleaning and ChartSpec 2.0 never appear in the chat manifest.

## Adding a tool

1. Add an `extra=forbid` Pydantic input with bounded parameters and explicit enums. Reuse the existing input components when applicable.
2. Return a category result from `models.py`. Table rows contain JSON scalars and typed column descriptors. Add a new typed model if the shape differs; avoid arbitrary dictionaries for results.
3. Implement a pure calculation accepting `(context, typed_input)`. Reuse `operations.py`, numeric validators and `table_output`. Validate size estimates before allocating derived matrices; do not truncate a full result to conceal a budget violation.
4. Register a FunctionTool explicitly in `catalog.py`, supplying category, capability tags, input/output model, required grants, timeout and whether it transforms data. Duplicate names, missing model classes and inconsistent transform permissions are rejected.
5. First add failing tests, then implement; run module and related regression tests. Add the tool to the exhaustive canonical contract test. Cover renamed fields, empty/missing input, incorrect types/parameters, finite/overflow behavior and unchanged input DataFrames.
6. Regenerate the catalog with `python scripts/generate_tool_catalog.py` from `backend/`. Only implemented, tested registrations belong in Available.

Registry supports get/list/category search/capability search/input validation/calculation/execution/permission-filtered manifests. `ToolMetadata` references the models through AnalysisTool's `input_schema` and `output_schema`; model classes are not persisted in JSON metadata. Legacy `avg/count_distinct` mapping exists only at adapter boundaries.

## Calling the engine

```python
import pandas as pd
from app.analysis.context import DatasetContext
from app.analysis.engine import AnalysisEngine, ExecutionContext
from app.analysis.models import ToolExecutionRequest

context = DatasetContext.from_frame(pd.DataFrame({"metric": [10, 20]}), dataset_id=1)
request = ToolExecutionRequest(
    tool_name="aggregate", dataset_id=1, request_id="example",
    parameters={"metrics": [{"column": "metric", "aggregation": "sum"}]},
)
result = AnalysisEngine().execute(request, ExecutionContext(user_id=1, dataset=context))
assert result.data.rows[0]["metric_sum"] == 30
```

Production callers submit through the infrastructure service after authentication, using `submit(user_id, request, trusted_permissions)`, then read via `get` / `read_artifact`. The queue invokes the fixed trusted worker entry. Do not invoke production calculations directly in request handlers to bypass process supervision. In-process Engine calls detect elapsed deadlines but cannot preempt a Pandas call; the supervised worker provides hard termination.

## Calculation and error contracts

Filters use field-aware scalar validation and literal string contains, with not_in/not_null included. Sorting is stable with missing values last. Aggregations use an enum; valid missing samples are skipped. All-missing numeric statistics return null with status/warnings; count/nunique return zero. ddof defaults to 1. First/last mean the first/last non-missing value in input order. Integer sums and integer rolling sums retain BIGINT precision and reject overflow.

Sequence tools require ordering. Rolling windows count observation rows; min_periods defaults to window size. Percentage change never forward fills; zero bases are null with a warning. Shares and growth are ratios; server facts render percentages. Weighted averages use valid pairs and nonnegative weights. Correlation uses pairwise valid samples (default minimum 3), returning method, coefficient, sample count and reason; Spearman uses average ranks without SciPy.

ToolError provides `code/message/details/recoverable/suggestion`. Output validation rejects nonfinite numbers, malformed table totals/shapes, mismatched full frames and invalid correlation structure/ranges. Unexpected provider, driver and calculation exception text is not a public message. Legitimate empty statistics remain structured; overflow cannot become a successful null statistic.

## Budgets, versions and compensation

Settings: TOOL_PREVIEW_ROWS=100 (maximum 500), TOOL_MAX_ROWS=100000, TOOL_MAX_COLUMNS=200, TOOL_MAX_CELLS=40000, TOOL_CORRELATION_COLUMNS=50. Existing DataFrame/artifact byte budgets remain. Charts allow at most 80 series and 500 points per series. Requests may explicitly choose a bounded preview limit. Artifact payloads retain complete results; responses contain the bounded rows, true row_count, truncated and artifact_ref.

0007 extends execution records and artifact ownership. Agent attempts and standalone tasks both record tool version, normalized input, pinned dataset version, times, status, safe error and result/artifact reference. User/request id defines idempotency; changed content conflicts, and failed transforms do not automatically retry.

Transform publication reserves server-generated projection and artifact cleanup references durably, validates candidate data, writes an independent projection (`if_exists=fail`), then locks Dataset and checks owner/lease/source_version=current. A successful transaction creates the child version and synchronizes current metadata. Losing publishers fail with DATASET_VERSION_CONFLICT and require an explicit retry. Interrupted/failed tasks activate compensation for unpublished projections/files. Existing projections, historical versions and accepted original files remain. Dataset deletion collects all versions and artifacts through existing retryable CleanupTasks.

Schema.storage_type is optional for old versions. Its fallback uses that version's own dtype/semantics. SQL accepts only the existing logical dataset_ID table and approved fields/functions; server AST mapping selects the pinned physical projection. Clients cannot request arbitrary physical table names.

ChartSpec 2.0 is internal, with eight typed chart kinds and a small options whitelist. Old generate_chart returns the existing five-kind ChartSpec 1.0. The Vue business code and historical result JSON are preserved.
