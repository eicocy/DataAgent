# 演示验收

确认迁移、账号、任务执行器、Key 和 Origin 已配置；检查 `/health/live`、`/health/ready`。缺少 Key 应明确失败，不出现模拟答案。

1. 注册登录，上传 `sample-data/sales_demo.csv`，等待解析完成。
2. 核对 order_date/product/sales 字段、预览和质量警告。
3. 提问：“分析最近六个月不同产品销售额变化，找出增长最快的三个产品并生成趋势图”。
4. 检查窗口、筛选、月度汇总、排名、图表和报告步骤。
5. 刷新恢复任务；断网重试复用 request_id，不能新增计算。
6. 在历史核对结果来源、参数、耗时及终态，导出图表 PNG。

窗口以数据最大日期所在月为末月。sales_demo 最大日期 2026-05-05，对应 2025-12 至 2026-05；缺少首末月的产品不能假装有增长排名。

确定性验收使用 `sample-data/sales_growth_demo.csv`：A 100→200（100%）、B 100→150（50%）、C 100→120（20%），D 首月 0、E 缺首月排除。末月 2026-06，前三名 A/B/C。趋势图必须引用完整月度数据，缺失月份保持缺失。

失败验收涵盖非法日期、缺失月份、写 SQL、跨用户任务/图表访问、图表失败、模型超时、服务重启。有真实计算但后续必需步骤失败应 partial，不能 succeeded；已提交步骤仍可核对。

记录测试命令、API URI/状态/类型、任务 ID、Trace、数值及图表截图；不保存 Key、Cookie、连接串或敏感数据。Mock 测试不是真实模型证明。

## 2026-10-02 实际验收

- MySQL8.0.46冷启动、应用/投影/只读/迁移账号初始化、迁移head0005、镜像构建和healthready200通过。
- 带真实MySQL测试连接和显式SECRET_KEY运行全后端测试，82 passed；包含0001已有记录→0003→0005、日期/Decimal/JSON及只读跨库权限。
- HTTP注册201、上传202、后台解析ready、22行预览200；缺Key任务202后最终failed/MODEL_UNAVAILABLE，answer为空；相同request_id返回同一记录。
- down保留卷后up重新创建所有容器，用户登录、22行投影与失败历史保留。
- 真实上传投影的确定性工具返回A/B/C增长率1/0.5/0.2，排除2产品，3趋势系列各6点，真实只读SQL返回5产品。
- 旧投影脚本真实验收：干运行不建目标表；apply复制2行并保留DATE/DECIMAL(12,2)，核对行数后切换元数据、源表保留。

项目 `datalens-accept-eb86bed9` 保留运行于localhost8088，本机8080已被FlClash占用，Compose通过FRONTEND_PORT配置端口与Origin。私有凭据及测试runner保存在忽略目录 `.superpowers/sdd/production-upgrade/`。首次验收的真实容器浏览器完成登录、上传、解析、预览页面、任务提交、缺Key终态、刷新与历史，见evidence/browser-live.json。

随后用户配置deepseek-flash和Key，真实“按地区汇总销售额，并生成柱状图”任务通过计划、计算、图表与总结（任务5、会话5），见evidence/model-live-plan.json。5个地区的汇总与投影原值、图表与汇总结果均一致。修复了计划纠正反馈过于笼统的问题：只反馈有界Schema路径与错误类型，不包含原始值；仍拒绝未知字段和非法JSON。新增3项回归后全后端85项通过。六个月增长任务的真实模型演示仍需单独验收。
# 本地确定性证据

`python backend/scripts/demo_contract.py --output docs/evidence/sales-growth-local.json` 在仓库根目录执行，使用公开销售样例和固定计划验证真实月度计算、排名与趋势图。不会连接 MySQL 或调用模型；报告因未调用总结模型明确为 partial。已生成证据文件包含计划、工具参数、数值和图表来源。
