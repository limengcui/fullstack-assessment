# Full-stack assessment — Variant Studio

Python + FastAPI + SQLite + React + TypeScript。包含库存台账、履约优化、Xero 集成审查和可运行的多规格商品详情页。

## 快速开始（Windows PowerShell）

要求 Python 3.11+、Node.js 22+。

```powershell
cd D:\lgy\code\fullstack-assessment
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
cd app/frontend
npm ci --cache .npm-cache
npm run build
cd ../..
.\.venv\Scripts\python.exe -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://127.0.0.1:8000 。商品 ID 为 `1`。构建后前后端由一个服务提供。也可在根目录运行 `./start.ps1`，依赖已安装时会构建前端并启动后端。

开发模式：一个终端启动上述后端，另一个在 `app/frontend` 执行 `npm run dev`，打开 http://127.0.0.1:5173 。Vite 转发 `/api` 到后端；图片来自本地 public 文件。

## 自动化检查

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd app/frontend
npm test
npm run build
npm run test:e2e
```

算法输入可以用管道传入：`Get-Content input.txt | .\.venv\Scripts\python.exe -m A.solution`，B 对应 `-m B.solution`。

## 目录

- `A/solution.py`：库存状态机。
- `B/solution.py`：履约分配 DP。
- `C/answers.md`：六项 Xero 集成回答、参考资料与验证边界。
- `app/backend/main.py`：API、SQLite 初始化和事务。
- `app/frontend/src/`：API 客户端、领域类型、界面及交互测试。
- `tests/`：算法对照测试和后端并发测试。

## A：约定与复杂度

维护实际库存、预留总量、订单预留映射、已处理事件集合。格式检查完成后才占用事件 ID；业务拒绝仍占用。重复合法事件忽略载荷差异，返回 DUPLICATE。数量只接受 ASCII 十进制正整数字符串。格式错误返回 REJECTED 且不消耗事件 ID；非法首行向 stderr 写错误并以非零状态退出。

末尾格式约定为 `OPEN K`，后跟 K 行 `order_id quantity`。只保留正预留，按 ASCII ID 排序。每条命令平均 O(1)，全部 O(N)，末尾另需 O(K log K) 排序；空间 O(N+K)。Python 整数支持累计库存超过单条数量上限。

## B：状态、优化与证明

比较 `(使用仓库数, 总成本, 排序后的 (warehouse_id, allocated_quantity) 元组列表)`；数量按整数比较。仓库 ID 唯一、ASCII、区分大小写。先按 ID 降序处理，以便把新仓库前置到已有方案。

`dp[q]` 表示已处理仓库恰好提供 q 件时的最优三元组。当前仓库容量 s、固定成本 f、单位成本 u；不使用时保留旧状态，使用时从 `t in [q-s, q-1]` 转移：仓库数加一，成本为 `old_cost[t] + f + (q-t)*u`。

滑动窗口按 `(old_count[t], old_cost[t]-t*u, -t)` 维护单调队列。前两项先优化数量与成本，平局时较大的 t 产生较小的当前仓库分配量。因为当前仓库 ID 小于已有所有 ID，当前数量先决定字典序；相同 t 的旧方案已经最优。最后再与不使用当前仓库的完整三元组比较。

转移数量 O(WQ)，每个窗口元素只入队/出队一次。方案使用长度不超过 W 的元组保存，复制和比较的最坏代价 O(W)，因此完整实现最坏时间 O(W²Q)、空间 O(WQ)；不会枚举全部仓库子集。最大约束 W=30、Q=2000。测试使用 300 组固定随机种子的小问题与穷举对照，另包含最大规模及字典序案例。

## 应用模型和事务

商品包含颜色/尺码两个维度、8 个真实 SKU、一个缺货 SKU，Forest/S 不存在。价格以整数美分保存，所有价格和可用库存均由服务端决定。图片为项目内自制 SVG，无第三方图片依赖。

加购立即预留库存。SQLite `BEGIN IMMEDIATE` 将请求去重、库存更新、购物车更新、响应持久化放在同一事务内，跨线程/进程串行化写入；库存表也有非负约束。相同购物车和请求键重复执行返回原响应；载荷不同返回 409。业务 404/409 也缓存，422 不缓存。数据库提交后响应丢失时，可用原键重放。

`X-Cart-ID` 是浏览器 localStorage 中随机 UUID，仅用于无登录演示的购物车隔离，不是身份认证。API 不对公网开放。幂等键按购物车隔离；演示中不自动过期。没有购物车删除、预留超时、结算或后台清理，库存预留持久存在。默认数据库为 `app/backend/store.db`，可用 `DATABASE_PATH` 指向其他文件。种子数据仅插入不存在的 SKU，不在重启时重置库存。停止服务后删除演示数据库及相关 WAL/SHM 文件可重置。

前端请求超时或网络失败时保留请求内容和幂等键，冻结规格并允许安全重试；收到明确业务拒绝后清除旧键并按服务端库存修正界面。成功响应更新对应 SKU 和购物车。页面加载错误及购物车错误可分别重试，不需要整页刷新。

## API 契约

除商品读取外，购物车请求需要 `X-Cart-ID`，加购还需 `Idempotency-Key`。请求/响应为 JSON。所有请求均返回 `X-Request-ID` 便于定位；事务中保存的业务错误不含请求级 ID，可用响应头关联。

### GET /api/products/1 → 200

```json
{"id":"1","name":"The Everyday Tee","description":"...","currency":"USD","options":{"color":["Ocean","Sand","Forest"],"size":["S","M","L"]},"skus":[{"id":"ocean-s","color":"Ocean","size":"S","price":4900,"stock":8,"image":"/images/ocean.svg"}]}
```

示例缩略，真实响应有 8 个 SKU。未知商品返回 404 `PRODUCT_NOT_FOUND`。

### POST /api/cart/items → 200

请求头：`X-Cart-ID: demo-cart`、`Idempotency-Key: unique-operation-1`。

```json
{"sku_id":"ocean-s","quantity":2}
```

```json
{"cart":{"items":[{"sku_id":"ocean-s","quantity":2,"price":4900,"color":"Ocean","size":"S"}],"total_item_count":2,"total_price":9800,"currency":"USD"},"sku_id":"ocean-s","available_quantity":6}
```

重放原键返回原结果和 `Idempotency-Replayed: true`。客户端不能附带价格或库存，额外字段会被拒绝。

### GET /api/cart → 200

请求头：`X-Cart-ID: demo-cart`，返回上述 `cart` 对象本身，`total_item_count` 是件数而不是 SKU 行数。

### 错误响应

```json
{"error":{"code":"INSUFFICIENT_STOCK","message":"Stock changed. Please choose a smaller quantity.","details":{"available":0}}}
```

| HTTP | 错误码 | 行为 |
|---|---|---|
| 422 | INVALID_INPUT | 缺请求头、数量不是整数/越界、额外字段；不改变状态 |
| 404 | PRODUCT_NOT_FOUND / SKU_NOT_FOUND | 商品或 SKU 不存在 |
| 409 | INSUFFICIENT_STOCK | 库存不足，details.available 提供最新数量 |
| 409 | IDEMPOTENCY_CONFLICT | 同一键对应不同请求内容 |
| 500 | INTERNAL_ERROR | 结构化通用错误，不泄露内部异常 |

OpenAPI：`/docs`。

## 测试范围与限制

后端覆盖示例、非法输入原子性、幂等冲突、购物车隔离、缺货、8 个并发请求抢最后一件以及同键并发重放。前端覆盖规格解析、价格和数量联动、重复点击、网络重试键复用及加载恢复。构建执行严格 TypeScript 检查。

SQLite 适合本地单机评估，不代表高吞吐生产存储。不存在真实支付、用户认证、外部 Xero 同步程序；C 是书面设计。未宣称真实 Xero 端到端验证。日志只记录异常类型和请求标识，不写凭据或客户信息。

## AI 使用披露

本项目由 OpenAI Codex 辅助生成实现、测试、界面和文档。提交者应阅读并理解所有设计，独立确认测试与约束，并能解释或修改代码。


## 浏览器验收与开发工具

`npm run test:e2e` 在 8010 端口启动临时测试服务和隔离数据库，使用本机 Chrome 检查 1280px、375px 加购以及外部并发导致的缺货恢复。运行前先 `npm run build`，需要本机已安装 Chrome，端口 8010 空闲。截图位于 `app/frontend/test-results/`，测试结束会关闭服务。

格式检查：根目录 `.\.venv\Scripts\python.exe -m ruff format --check A B app/backend tests`；前端 `npm run format:check`。

网络状态不确定时的请求键保存在页面内存，刷新/关闭页面会丢失该恢复上下文；演示未实现跨刷新 outbox。这是已知限制，未知结果时应使用页面中的安全重试。

## 本机验证记录

- Python 3.13.13、Node.js 22.20.0。
- Python：10 项测试通过。
- 前端：6 项交互/领域测试通过。
- Chrome：3 项端到端测试通过。
- TypeScript 严格检查及生产构建通过。
- 前端依赖审计：0 个已知漏洞（安装时结果）。
- Task B 最大规模示例约 0.03 秒，性能数字仅代表本机单次测量。
- 测试依赖存在 Starlette/httpx 的弃用提示，不影响当前测试结果；后续升级需重新验证兼容性。
- Git 已初始化，未创建远端仓库或上传代码。此主机运行身份和目录所有者不同，若 Git 报 ownership 错误，可在单次命令附带 `-c safe.directory=D:/lgy/code/fullstack-assessment`；未修改用户全局 Git 配置。
