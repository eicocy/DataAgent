# 安全边界

所有数据集、会话、任务、工件和图表都需要认证与资源所有权检查。模型输出是非可信输入；未知工具、额外参数、无效依赖和越权引用必须拒绝。

| 账号 | 数据库 | 权限 |
|---|---|---|
| datalens_app | datalens_agent | SELECT、INSERT、UPDATE、DELETE |
| datalens_migrate | datalens_agent | 迁移所需 DDL/DML |
| datalens_projection | datalens_data | CREATE、DROP、INSERT、SELECT |
| datalens_readonly | datalens_data | SELECT |

运行应用不携带 MySQL root 密码。初始化只在空卷执行，拒绝占位密码；限定安全字符同时避免 SQL 注入和 URL 凭据解析歧义。只读账号需要真实 MySQL 验证：能读投影，不能写，不能读业务表。

本机 MySQL 8.0 的应用账号采用 mysql_native_password，避免无 TLS 的开发网络需要额外 RSA 登录依赖；MySQL 不发布宿主端口。正式部署应使用 TLS 和供应商支持的认证方式，不能将本机开发设置当作生产认证策略。CI 的管理员连接额外安装 cryptography 以兼容默认 MySQL 8 登录。

SQL 首期拒绝 JOIN、CTE、子查询、UNION、变量、锁、文件输出和写语句。字段、函数、LIMIT、结果字节和超时分别约束，AST 不能替代数据库权限。

上传文件名不作为路径或表名。工件采用服务器生成路径下的带类型 JSON，不执行任意代码、不使用 pickle。缺失值不补零，无法解析日期保留原值并说明。上传样例和工具摘要可能发送到模型供应商，页面不能声称上传数据从不进入模型上下文。

普通日志仅记录标识、状态、耗时及安全错误；授权 Trace 可包含当前用户参数/证据，不写入普通日志。Cookie 使用 HttpOnly/SameSite=Lax 和 Origin 校验；对外部署需 HTTPS、Secure Cookie、随机 SECRET_KEY、准确 Origin。

固定子进程是超时控制，不是任意代码沙箱。单实例调度不提供多副本高可用承诺。工件过期后明确显示过期，历史快照不能冒充完整可引用数据。

2026-10-02 的真实MySQL验收确认只读账号可以读独立投影库、INSERT被拒绝、跨库users/password_hash读取被拒绝，错误码为权限拒绝；迁移和类型测试在隔离 datalens_test_* 数据库执行。Compose冷启动与卷恢复通过，随机凭据仅保存在Git忽略的私有env。没有提供模型Key，因此真实模型调用未执行。本说明与测试不是渗透测试或生产安全认证。
