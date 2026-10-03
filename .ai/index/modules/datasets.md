# datasets

## Files

backend/app/datasets/{schemas,profiler,versions}.py
role: 独立 Schema/Profile、语义与角色、初始版本和幂等旧投影回填
symbols: DatasetSchema、DatasetProfile、column_storage_type、build_profile、create_initial_version、backfill_dataset
depends: Pandas/Pydantic；versions 的存取边界依赖 SQLAlchemy 与 DatasetService

backend/app/routers/datasets.py
role: 上传/列表/字段/预览/删除；资源权限与任务提交
symbols: router
depends: Dataset、DatasetColumn、DatasetService、认证依赖

backend/app/services/datasets.py
role: 文件解析、类型恢复、质量警告、投影与数据加载
symbols: DatasetService、parse_file、safe_column_names、profile_frame、process_dataset、projection_table
depends: Pandas、openpyxl、SQLAlchemy、models、database

## Flow

上传路由 -> 服务器文件名 -> Dataset -> 解析任务 -> parse_file/profile_frame -> dataset_<id> 投影与版本 1 -> ready -> 授权固定版本加载 -> DatasetContext

清洗新版本使用独立 dataset_<id>_v_<server UUID> 投影；读取旧版本只用它自己的 Schema；不替换旧表或原文件。

## Related

backend/app/tools/pandas_tools.py；backend/app/models.py；frontend/src/views/DatasetDetailView.vue；backend/tests/test_dataset_service.py

backend/scripts/migrate_projections.py：旧投影反射复制、计数核对与定位切换，默认干运行。
