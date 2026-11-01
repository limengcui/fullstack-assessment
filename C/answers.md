# Task C — Xero integration review

核对日期：2026-11-01。假设采用 OAuth 2.0 authorization-code 多租户集成、Accounting API `/api.xro/2.0`、直接 HTTP 调用，不依赖特定 SDK；不采用 Custom Connections。以下为设计方案，未连接真实 Xero 组织进行实测。

## C1 — Connection verification

1. 从组织绑定记录读取令牌和预期 tenant ID，检查有效期；必要时在单飞锁内刷新，原子保存轮换后的 token，避免工作进程相互覆盖。
2. `GET https://api.xero.com/connections`，使用 Bearer token、JSON Accept；成功只能证明 token 可以枚举连接。按预先绑定的 `tenantId` 和类型匹配，不取数组第一项；找不到则要求重新连接，禁止静默切换组织。
3. 对选中组织调用 `GET https://api.xero.com/api.xro/2.0/Organisation`，携带 `Xero-tenant-id`；验证返回组织身份。该成功不证明发票读取权限。
4. 检查授权记录中的实际 granted scopes，再进行 `GET .../Invoices?page=1&pageSize=1` 只读探测。成功才证明当前组织的发票读取路径可用；空列表也是成功。组织探测需要对应权限，不能为此无条件扩大授权。

依据：[Tenants](https://developer.xero.com/documentation/guides/oauth2/tenants/)、[OAuth overview](https://developer.xero.com/documentation/guides/oauth2/overview)、[Token types](https://developer.xero.com/documentation/guides/oauth2/token-types/)。

## C2 — Failure diagnosis

首先保留脱敏的状态码、错误码、关联 ID、目标环境和路径模板，确认请求确实发往预期 Xero 主机，而非本地代理返回错误。

- **401**：检查 Authorization 格式、token 有效期、时钟偏差及刷新记录；允许单飞刷新后重试一次。刷新失败或再次 401 则暂停该连接并要求重新授权，不能无限刷新。
- **403**：比较实际 granted scopes 与所需读写权限，检查授权用户在该组织的角色及权限是否变化；复核 tenant header 是否属于本次 token 的连接。修复授权前不自动重试。新粒度权限可参考 `accounting.invoices.read`（读）、`accounting.invoices`（写），旧应用可能仍涉及 `accounting.transactions`；新粒度权限可参考 `accounting.invoices.read`（读）、`accounting.invoices`（写），旧应用可能仍涉及 `accounting.transactions`；scope 名称可能随应用迁移变化，应依据实际应用和当前文档确认，不能只改配置中的 scope 字符串而不重新授权。
- **404**：核对 API 基础路径、复数资源路径、资源 ID 类型、组织归属和环境配置；单条资源失败时先验证集合端点。不能推断“404 就是被删除”，更不能跨租户搜索。
- **环境差异**：逐项比较 app/client ID、回调配置、连接映射、secret 版本、代理规则和部署配置，使用脱敏配置摘要，不输出凭据。

connections 成功不排除后续权限不足、组织选择错误或 token 在两次请求之间过期。错误诊断应结合响应正文，而非只按状态码下定论。

## C3 — Resumable incremental synchronisation

按组织持有带 fencing token 的同步租约，防止同一组织多个工作进程同时推进游标。首次全量分页，之后以持久化水位减去可配置重叠窗口作为 `If-Modified-Since`，采用稳定的更新时间/InvoiceID 排序。分页与时间筛选的依据见 [Invoices](https://developer.xero.com/documentation/api/accounting/invoices)。

本地唯一键为 `(tenant_id, InvoiceID)`，按版本时间 upsert，同版本重放无副作用；外发副作用使用唯一 outbox 键。每页的数据写入和页检查点在同一本地事务提交，页失败不前进。单条无法解析的数据持久化到隔离队列并告警，不能静默丢弃后宣布同步完整。

页号不是快照游标，源数据在分页期间可能移动。运行中保存页号仅作进度；崩溃恢复优先从已提交水位的重叠窗口第一页重新扫描。完整扫描成功后才推进全局水位，使用扫描开始时刻作为保守上界；不能用失败页之后见到的最大时间直接跳过数据。

重叠窗口只降低漏数概率，不保证任意并发变更下的严格快照。需周期性更宽范围/全量对账，并对关键发票主动按 ID 查询。官方说明部分字段变化不更新修改时间，因此 modified-since 不能代表所有业务变更，见 [Requests and responses](https://developer.xero.com/documentation/api/accounting/requests-and-responses/)。

## C4 — Rate limits

429 时优先解析 `Retry-After` 并延迟至少该时长；缺失或非法时采用有上限的指数退避和 full jitter。读取可用限额响应头以降低后续速率，而非等到 429 才控制。限额值按应用档位配置，不把数字写死。

共享调度器对每组织实施并发上限和令牌桶，再设应用级上限；一个组织冷却时允许其他组织公平运行。长等待任务重新入队并持久化 `next_attempt_at`，不占住工作线程。设置总重试次数和最长任务年龄；耗尽后进入可观察的失败队列。

网络故障和 5xx 仅对安全读取或受幂等保护的写入重试；400 校验错误、403 权限问题、404 配置/资源错误不盲目重试；401 仅允许一次受控刷新。批量响应也必须检查逐条结果。

依据：[Rate limits](https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/)、[FAQ](https://developer.xero.com/faq)。

## C5 — Data integrity

为 `(tenant_id, internal_order_id, operation_version)` 建立唯一发送记录，在本地事务写业务状态和 outbox。发送前持久化不可变的请求内容摘要、唯一请求键和状态，租约只允许一个发送者。

对支持的创建接口发送 `Idempotency-Key`，同一操作的网络重试复用相同键、HTTP 方法、URL 和请求体。Xero 文档说明其键缓存只有 6 分钟，因此不能将远端缓存当作永久去重机制，见 [Idempotent requests](https://developer.xero.com/documentation/guides/idempotent-requests/idempotency/)。

成功后保存 Xero InvoiceID 与内部订单映射。超时进入 UNKNOWN，先使用相同键在有效窗口内安全重试；超过窗口则先对账。使用确定性的销售发票编号（若业务允许）和引用定位候选，核对组织、客户、金额、币种和明细，确认唯一匹配后补记映射。Reference 不是唯一约束，不能仅凭它认定成功。零个候选也不能立即证明未创建，需考虑查询延迟；多候选或无法确认时暂停并人工处理，禁止自动再创建。

## C6 — Observability and security

日志只记录操作类型、内部连接标识、job/run/attempt ID、内部订单标识的脱敏值、HTTP 状态、结构化错误分类、耗时、分页位置和远端关联 ID。记录水位推进与重试决策，便于审计；不记录完整请求/响应负载。

指标包括组织同步延迟、队列年龄、成功/失败率、429 比例、重试预算耗尽、刷新失败、UNKNOWN 创建数和待对账数量。针对持续落后、权限失效、未知结果积压和凭据刷新异常告警。指标标签避免使用无限增长的订单 ID。

禁止记录 access/refresh token、client secret、Authorization、完整发票个人信息和财务明细。凭据用 KMS/secret manager 加密，按组织隔离与最小权限访问；刷新 token 原子轮换，secret 使用版本化发布和受控切换。撤销连接后停止任务并按保留策略删除凭据；备份和日志也遵循访问控制与保留期限。

## Verification boundaries

官方站点部分页面依赖 JavaScript；本次结合可检索的官方页面正文核对。未验证真实账户权限、端点的全部错误组合或授权迁移状态。上线前必须用测试组织验证所选权限、分页边界、刷新竞争及幂等缓存边界，并将使用的 SDK/OpenAPI 版本固定。

补充官方依据：[Troubleshooting](https://developer.xero.com/documentation/guides/oauth2/troubleshooting/)、[Managing tokens](https://developer.xero.com/documentation/best-practices/data-integrity/managing-tokens/)、[Granular scope changelog](https://developer.xero.com/changelog)。

补充官方依据：[Troubleshooting](https://developer.xero.com/documentation/guides/oauth2/troubleshooting/)、[Managing tokens](https://developer.xero.com/documentation/best-practices/data-integrity/managing-tokens/)、[Granular scope changelog](https://developer.xero.com/changelog)。
