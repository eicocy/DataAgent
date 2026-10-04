# V2.0.5 运行与升级手册

这是部署准备与恢复流程，不表示生产部署或业务库迁移已经执行。当前系统保持单实例监督器、单 worker；进程中断终结旧任务并保留已完成证据，不跨重启续跑计算。迁移头仍是 `0012_artifact_workspace`。

## 默认部署与能力

普通 `docker compose up --build -d` 使用既有 MySQL、迁移、后端和 Nginx，沙箱默认关闭。普通工具、报告与下载不依赖 Docker broker。`GET /api/v1/workspace/capabilities` 的 `sandbox.status` 区分 disabled / available / unavailable；已配置不等于可用，启用后会验证 broker 协议及健康。无任意代码的公开接口。

上线前核对 `.env.example` 并为数据库账号、SECRET_KEY 配置不同随机密码，不把模型 Key 放进源码或镜像。使用只读数据库账号执行 SQL。前端只绑定本机 HTTP 端口；远程访问需自行配置受信任 HTTPS 反向代理并同步 FRONTEND_ORIGIN，不关闭 Origin/认证校验。Nginx 对 SSE 关闭缓冲/缓存，保留请求体上限与超时。

## 可选 Python 沙箱

先在隔离环境构建并验证执行镜像，单独生成 32 字符以上 `SANDBOX_BROKER_TOKEN` 放在本机环境文件，然后使用：

```powershell
docker compose -f compose.yaml -f compose.sandbox.yaml --profile sandbox config --quiet
docker compose -f compose.yaml -f compose.sandbox.yaml --profile sandbox up --build -d
```

覆盖文件只为应用启用 broker，不修改业务数据库。镜像初始化服务完成构建后退出；只有 broker 挂载 Docker socket，后端及执行容器不挂载 socket。broker 没有宿主端口，仅在 internal 控制网络可达。只部署一个 broker，不复制该服务；多个 broker 会把同一 scope 的旧容器视为重启遗留。

执行容器固定非 root、只读 rootfs、none 网络、cap_drop ALL、no-new-privileges；1 CPU、512 MiB、memory-swap 同为 512 MiB（无额外 swap）、64 PID、最多 60 秒。输入为授权固定版本的内存快照，没有上传目录、模型 Key、数据库连接或其他用户文件。输出 tmpfs 64 MiB，JSON/完整表格与最多四幅 PNG 经校验后入既有 Artifact/报告；PNG 解码并重新编码，拒绝 SVG、路径、链接、非有限值及错误表格。限制依据 [Docker 资源约束](https://docs.docker.com/engine/containers/resource_constraints/) 与 [容器运行选项](https://docs.docker.com/engine/containers/run/)。

普通注册工具优先，最多两次受控规划仍找不到对应方法时才提出受限代码；参数错误、清洗发布和已有工具不会获得代码执行授权。应用与 broker/runner 各做 AST 校验；禁止系统/网络/进程/动态导入、eval/exec、pickle 和任意文件读写。结果来自自定义方法，需要用户核对统计前提；攻击测试不是安全认证，Docker 容器也不是专用于高对抗多租户的虚拟机边界。

任务取消/租约失效会请求销毁，客户端停止续租后 broker 最多五秒清理；broker 重启仅清理自身 scope 的执行容器。broker 不可用、内核缺少限额或镜像协议不匹配时明确失败，不回退宿主执行。导出 Python 重现自定义方法同样需要 broker；专用令牌只从环境读取，不写进脚本。

## 一致性备份

先停止接收新任务并等待/取消活动任务，然后停止 backend（保留 MySQL 和卷），备份应用库、投影库及 `/data/uploads`、`/data/artifacts`。MySQL 两库必须在停止应用写入期间按顺序备份；`--single-transaction --routines --triggers --hex-blob --set-gtid-purged=OFF --no-tablespaces`。通过 `MYSQL_PWD` 环境传密码，不在参数/发行日志输出密码。将两库分别生成 SQL 并保留版本、迁移头、备份时间、文件计数；环境凭据另用受控方式备份，不塞进公开源码。

`deploy/backup.py` 接收已生成的数据库 SQL dump 和数据目录，流式生成带 SHA-256 manifest 的归档并复验。多数据库分别打包并登记配对关系；它不自动连接或恢复数据库。示例：

```powershell
python deploy/backup.py bundle --database-dump backup/application.sql --data-dir backup/data --output backup/application.zip
python deploy/backup.py verify backup/application.zip
python deploy/backup.py restore-files backup/application.zip --target-dir backup/restore-check
```

恢复文件只允许空目标目录，拒绝路径穿越、符号链接、重复条目、校验不一致及过大归档，不覆盖现有数据。备份含用户数据，放在受限磁盘并按需要加密；ZIP checksum 不提供加密或来源认证。不要把备份、上传数据和工件加入 Git。

## 升级与恢复演练

1. 在独立空数据库和数据目录恢复 SQL 与文件；确认两库、上传和 Artifact 属于同一次停写备份。
2. 设置 MIGRATION_DATABASE_URL 为该隔离库，执行 `alembic upgrade head`。从 0009 升到 0012，检查旧记录、固定版本、血缘与文件；不要通过 downgrade 回滚有持久成果的数据。
3. 启动隔离服务，检查 `/health/live`、`/health/ready`、能力目录、用户登录、旧结果、报告预览和认证下载。SSE 断连后按 Last-Event-ID 重连；重启前活动任务应终结，旧结果不能被迟到 Worker 覆盖。
4. 用小模拟数据验收分析、Artifact 与 PDF/DOCX/XLSX；如启用沙箱，另检查隔离、OOM、超时、取消、租约过期和重启无残留。
5. 演练通过后再对正式环境停写、备份、迁移和替换服务。若需回退，恢复配套数据库与文件快照及原镜像；恢复目标必须明确且事先保留现有数据，不执行 `docker compose down -v`。

## 检查与故障

普通 CI 不调用付费模型，使用固定 Provider 验证规划/事实绑定；Linux sandbox job 独立构建镜像并运行受限 Docker 验收。真实模型验收另记环境、模型、用量和失败，不把离线检查当作模型通过。

SANDBOX_DISABLED/UNAVAILABLE：核对能力状态、配置与 broker 健康。SANDBOX_OOM/TIMEOUT/OUTPUT_LIMIT：缩小数据或方法，保持固定上限。SANDBOX_LEASE_EXPIRED/CANCELLED：原任务已失去授权，重新提交会产生新任务。仅查看错误码、记录 ID、耗时和安全 trace；不打印模型 Key、SQL 参数、原始代码/输入或 broker 令牌。Windows Docker 引擎无法启动时使用隔离 Linux 环境验收，禁止宿主回退。
