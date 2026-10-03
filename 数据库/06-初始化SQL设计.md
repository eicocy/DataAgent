# 初始化 SQL 设计

本文件只描述未来迁移顺序，不提供可直接执行的完整脚本。

1. 创建数据库并选择 `utf8mb4` 与一致排序规则。
2. 创建 users。
3. 创建 datasets，再创建 dataset_columns。
4. 创建 analysis_sessions。
5. 创建 analysis_messages。
6. 创建 analysis_records；其消息外键需要在 messages 之后。
7. 添加唯一约束、外键和组合索引。
8. 创建受控查询所需只读视图/映射（若采用 SQL Tool）。
9. 创建仅 SELECT 权限的 SQL Tool 数据库账号，与应用写账号分离。

状态默认值和长度必须与 Pydantic/SQLAlchemy Enum 同步。后续结构变更使用迁移工具，不手工修改生产库。
