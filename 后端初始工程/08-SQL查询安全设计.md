# SQL 查询安全设计

## 允许与禁止

只允许一条 SELECT（包含安全 CTE 时仍须最终为 SELECT）。禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE、REPLACE、GRANT、REVOKE、CALL、LOAD、INTO OUTFILE 和多语句。

## 防线

1. 使用 SQL parser/AST 判断语句类型，不用简单字符串前缀作为唯一判断。
2. 拒绝分号多语句、注释绕过、动态 SQL 和危险函数。
3. 表名必须属于当前 dataset 的只读视图白名单；列名必须来自 DatasetColumn。
4. 强制外层 LIMIT，最大 500；模型给出更大值时收紧。
5. 数据库账号只有 SELECT 权限，连接设置只读事务。
6. 查询超时默认 5 秒，限制返回字节和扫描风险。
7. 记录 query_hash、dataset_id、user_id、耗时和拒绝原因，不记录敏感值。

## 错误

向用户返回 `SQL_NOT_ALLOWED`、`SQL_UNKNOWN_TABLE`、`SQL_UNKNOWN_COLUMN`、`SQL_LIMIT_EXCEEDED`、`SQL_TIMEOUT` 等稳定错误码；不返回数据库连接、文件路径或原始堆栈。

SQL Tool 是补充能力。能用结构化 Pandas Tool 完成的任务优先使用 Pandas，减少模型生成 SQL 的必要性。

