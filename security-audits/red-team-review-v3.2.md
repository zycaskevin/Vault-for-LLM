# Vault-for-LLM 搜索功能红队安全审查 v3.2

**审查范围**: 搜索相关所有安全边界（输入验证、权限边界、资源消耗、旁路攻击、性能稳定性、缓存安全）  
**核心文件**: `vault/search.py`、`vault/db.py`、`vault/semantic.py`、`vault/graph.py`  
**上一版本评分**: v3.1 — 3.9/5  
**当前版本评分**: **4.1/5** — 多项修复已到位，仍存在若干中低危问题

---

## 总体评价

v3.1 中发现的 P1/P2 问题大部分已得到修复：
- ✅ FTS5 注入防护基本到位（`_quote_fts_token` 双引号包裹 + 转义）
- ✅ 参数验证机制已建立（`_validate_params`）
- ✅ 多层权限过滤（FTS/LIKE/向量均有 trust/layer/category 过滤）
- ✅ 输入长度限制（MAX_QUERY_LENGTH、MAX_INPUT_LEN）
- ✅ Token 数量限制（MAX_TOKENS = 100）
- ✅ 图譜扩展深度上限（MAX_GRAPH_EXPAND_DEPTH = 5）

但仍存在 0 个 P0、2 个 P1、4 个 P2、4 个 P3 问题需要关注。

---

## P1 — 高危问题

### P1-1: `get_neighbors` BFS 无结果数量上限 — DoS 风险

**位置**: `vault/db.py:1050` — `get_neighbors()` 方法

**原理**:
- BFS 遍历仅限制了最大深度（`MAX_DEPTH = 10`），但未限制返回的邻居节点总数
- 在密集图中，单个节点的 5 跳邻居可能达到数百甚至数千个节点
- 图譜扩展时，每个邻居都会调用 `get_knowledge()` 加载完整文档内容，内存和 CPU 消耗成倍增长
- `_apply_graph_expand` 仅在最后做 `expanded[:limit]` 截断，中间已处理了大量数据

**利用方式**:
```python
# 搜索一个高度连接的节点，并启用深层图譜扩展
search("highly_connected_topic", graph_expand=5, limit=10)
# 内部可能遍历并加载了数百个节点，最后只返回10个
```

**风险等级**: P1 — 可导致显著的性能下降和内存消耗，在大型知识库中可能形成 DoS

**修复建议**:
```python
# 在 get_neighbors 中增加结果数量限制
MAX_NEIGHBORS = 200  # 合理上限

# 在 BFS 循环中检查结果数量
for depth in range(1, max_depth + 1):
    next_frontier = set()
    for nid in frontier:
        # ... 现有逻辑 ...
        if len(results) >= MAX_NEIGHBORS:
            break  # 达到上限时提前终止
    if len(results) >= MAX_NEIGHBORS:
        break
    frontier = next_frontier
```

---

### P1-2: `query_expansion_count` 无上限 — 放大式 DoS

**位置**: `vault/search.py:520` — `VaultSearch.__init__` 和 `_validate_params()`

**原理**:
- `_validate_params` 仅验证 `query_expansion_count >= 0`，未设置上限
- 若攻击者可配置此参数（如通过 API 或配置文件），设置为极大值（如 10000）
- 每次搜索都会执行 N 次子搜索（keyword/vector/semantic/hybrid），计算量线性放大
- 结合图譜扩展时，危害进一步叠加

**利用方式**:
```python
# 配置极大的扩展数量
searcher = VaultSearch(db, query_expansion_count=10000)
searcher.search("test")  # 执行10000次子搜索
```

**风险等级**: P1 — 参数无上限导致计算资源被线性放大消耗

**修复建议**:
```python
# 在 _validate_params 中增加上限检查
MAX_QUERY_EXPANSIONS = 20
if self._query_expansion_count > MAX_QUERY_EXPANSIONS:
    raise ValueError(
        f"query_expansion_count 不能超过 {MAX_QUERY_EXPANSIONS}，"
        f"当前值: {self._query_expansion_count}"
    )
```

---

## P2 — 中危问题

### P2-1: 语义索引搜索的权限过滤在 Python 层而非 SQL 层

**位置**: `vault/semantic.py:197` — `search_semantic_index()` + `vault/search.py` — `search_semantic()`

**原理**:
- `search_semantic_index` 的 SQL 查询仅按 `provider_id`、`dimension`、`vector_kind` 过滤
- **未在 SQL 中加入 `trust >= ?`、`layer = ?`、`category = ?` 等权限过滤条件**
- 过滤全部在 Python 层通过 `if trust < min_trust`、`if layer != layer` 等判断完成
- 虽然最终数据不会泄露，但存在以下问题：
  1. **时序侧信道**: 攻击者可通过响应时间推断受限文档的存在性和数量
  2. **资源浪费**: 加载了大量被过滤掉的文档，消耗内存和 CPU
  3. **结果不足**: 若过滤掉大部分结果，实际返回数量可能远小于 `limit`

**当前代码**:
```python
# semantic.py — SQL 无权限过滤
rows = db.conn.execute(
    """SELECT sv.*, k.title, k.category, k.layer, k.trust, ...
       FROM semantic_vectors sv
       JOIN knowledge k ON k.id = sv.knowledge_id
       WHERE sv.provider_id=? AND sv.dimension=? AND sv.vector_kind=?
       ORDER BY sv.id
       LIMIT ? OFFSET ?""",  # ❌ 缺少 trust/layer/category 过滤
    ...
)

# search.py — Python 层后过滤
for row in rows:
    if item.get("trust", 0.0) < min_trust:  # ❌ 后过滤
        continue
    if layer and item.get("layer") != layer:  # ❌ 后过滤
        continue
    if category and item.get("category") != category:  # ❌ 后过滤
        continue
```

**风险等级**: P2 — 存在信息泄漏侧信道风险，且影响性能

**修复建议**:
```python
# 在 SQL 中加入权限过滤条件
where_conditions = [
    "sv.provider_id=?",
    "sv.dimension=?", 
    "sv.vector_kind=?",
    "k.trust >= ?",  # ✅ 新增
]
params = [provider_id, dim, vector_kind, min_trust]

if layer:
    where_conditions.append("k.layer = ?")  # ✅ 新增
    params.append(layer)
if category:
    where_conditions.append("k.category = ?")  # ✅ 新增
    params.append(category)
```

---

### P2-2: 错误消息可能泄露数据库内部结构

**位置**: 多处 `print` 异常信息的代码

**实例**:
```python
# vault/search.py — 向量搜索异常
except sqlite3.OperationalError as e:
    if self._is_vector_db_fallback_error(e):
        print(f"[vault-mcp] ⚠️ 向量搜尋失敗，降級到關鍵字: {e}")

# vault/search.py — 嵌入失败
except Exception as e:
    print(f"[vault-mcp] ⚠️ 嵌入失敗，降級到關鍵字: {e}")
```

**原理**:
- 异常消息直接包含原始数据库错误信息
- 可能泄露表名（`knowledge_vec`、`semantic_vectors`）、列名、配置细节
- 若应用暴露给不可信用户，这些信息有助于攻击者构造更精准的攻击

**风险等级**: P2 — 信息泄露为进一步攻击提供便利

**修复建议**:
```python
# 用户-facing 输出使用通用消息，详细错误仅内部日志
print("[vault-mcp] ⚠️ 向量搜尋暫時不可用，已降級到關鍵字搜尋")
# 详细错误写入日志（如 logging 模块）
logger.debug(f"Vector search failed: {e}")
```

---

### P2-3: 图譜扩展在最终截断前处理大量节点

**位置**: `vault/search.py:2236` — `_apply_graph_expand()`

**原理**:
- 函数首先获取所有邻居节点（可能有上百个），然后为每个节点调用 `get_knowledge()`
- 全部处理完成后才通过 `return expanded[:limit]` 截断
- 当 `limit` 较小（如 10）但邻居很多时，大部分处理是浪费的
- 结合 P1-1（`get_neighbors` 无上限），问题更加严重

**风险等级**: P2 — 不必要的资源消耗，放大 DoS 影响

**修复建议**:
```python
# 方案1：在 get_neighbors 层就限制数量（参见 P1-1）
# 方案2：在 _apply_graph_expand 中增量处理，达到 limit 后停止
seen_ids = {r["id"] for r in results}
expanded = list(results)

for r in results:
    if len(expanded) >= limit:
        break  # 已足够，提前终止
    neighbors = self.db.get_neighbors(r["id"], ...)
    for n in neighbors:
        if len(expanded) >= limit:
            break
        if n["id"] not in seen_ids:
            # ... 处理逻辑 ...
            expanded.append(d)
```

---

### P2-4: FTS5 查询中 OR 术语过多可能导致性能问题

**位置**: `vault/db.py:635` — `search_fts_keyword()`

**原理**:
- `_tokenize` 最多返回 100 个 token（MAX_TOKENS = 100）
- FTS5 查询构造为 `"term1" OR "term2" OR ... OR "term100"`
- 大量 OR 术语可能导致 FTS5 查询规划器效率下降
- 在大型知识库（百万级文档）上，这种查询可能变慢数倍

**当前缓解**: 已有 `MAX_TOKENS = 100` 限制，问题被控制在一定范围内

**风险等级**: P2 — 性能退化，不影响正确性但可能被利用为 DoS

**修复建议**:
```python
# 降低 MAX_TOKENS 或增加 FTS 查询复杂度限制
MAX_FTS_TERMS = 30  # 更保守的上限
terms_for_fts = terms[:MAX_FTS_TERMS]
```

---

## P3 — 低危问题

### P3-1: Cross-Encoder 缓存双重检查锁定模式

**位置**: `vault/search.py` — `CrossEncoderReranker._try_init()`

**原理**:
- 使用了双重检查锁定（Double-Checked Locking）模式
- 在 Python 中由于 GIL 的存在，该模式通常是安全的
- 但存在理论上的竞态窗口：两个线程同时首次调用时，可能重复加载模型
- 实际影响极小，最多导致一次额外加载，不影响正确性

**风险等级**: P3 — 理论上的竞态条件，实际影响可忽略

**修复建议**: 维持现状即可，或使用 `threading.local` 简化模式

---

### P3-2: 实体规则加载存在路径遍历潜在风险

**位置**: `vault/graph.py` — `_load_entity_rules()`

**原理**:
- `project_dir` 参数直接用于拼接文件路径：`Path(project_dir) / "entity_rules.yaml"`
- 若 `project_dir` 可被用户控制，可能存在路径遍历（如 `project_dir="../../etc"`）
- 当前场景下 `project_dir` 通常在初始化时设置，不由终端用户控制

**风险等级**: P3 — 仅在特定部署场景下有风险

**修复建议**:
```python
# 规范化路径并验证
project_path = Path(project_dir).resolve()
# 可选：验证路径在允许的目录内
# if not str(project_path).startswith(ALLOWED_BASE_DIR):
#     raise ValueError("Invalid project directory")
```

---

### P3-3: 无搜索速率限制

**位置**: 全局

**原理**:
- 搜索接口未内置速率限制
- 若应用通过 API 暴露，攻击者可能发起高频搜索请求导致资源耗尽
- 对于纯本地工具，此问题不适用

**风险等级**: P3 — 取决于部署方式，本地部署无风险

**修复建议**: 若提供网络 API，应添加速率限制中间件

---

### P3-4: 中文分词滑窗可能产生过多 Token

**位置**: `vault/search.py:2300` — `_tokenize()`

**原理**:
- 中文长文本采用双字滑窗，长度为 N 的中文串产生 N-1 个双字 Token
- 虽有 `MAX_TOKENS = 100` 限制，但全中文输入时 Token 质量不高
- 前 100 个 Token 可能只覆盖文本开头的 50 个汉字，丢失后面的语义

**风险等级**: P3 — 影响搜索质量而非安全

**修复建议**: 考虑采用更智能的中文分词策略，或对超过一定长度的中文进行采样

---

## 已修复问题验证（v3.1 → v3.2）

### ✅ FTS5 注入防护 — 已修复
- `_quote_fts_token` 正确使用双引号包裹 + 内部双引号转义
- Tokenizer 仅提取字母和中文字符，过滤特殊符号
- 查询扩展结果会再次经过 Tokenization，确保安全

### ✅ 参数验证 — 部分修复
- 权重参数 >= 0 ✅
- 衰减参数在 0-1 范围 ✅
- 策略值在白名单内 ✅
- **缺少**: `query_expansion_count` 上限（见 P1-2）
- **缺少**: `cross_encoder_model` 未验证格式

### ✅ 权限边界 — 大部分修复
- FTS 搜索：SQL 层有 trust/layer/category 过滤 ✅
- LIKE 搜索：SQL 层有过滤 ✅
- 向量搜索：SQL 层 + Python 层双重过滤 ✅
- 图譜扩展：双重过滤 ✅
- **问题**: 语义索引搜索缺少 SQL 层过滤（见 P2-1）

### ✅ 资源限制 — 部分修复
- 查询长度限制 ✅
- Token 数量限制 ✅
- Limit 上限 ✅
- 图譜深度限制 ✅
- **缺少**: 邻居数量上限（见 P1-1）
- **缺少**: 查询扩展数量上限（见 P1-2）

---

## 修复优先级建议

| 优先级 | 问题 | 预计修复时间 | 影响 |
|--------|------|-------------|------|
| 🔴 高 | P1-1 get_neighbors 无数量上限 | 30 min | 防止图譜 DoS |
| 🔴 高 | P1-2 query_expansion_count 无上限 | 10 min | 防止放大式 DoS |
| 🟡 中 | P2-1 语义索引 SQL 层缺少权限过滤 | 1-2 h | 修复侧信道 + 性能提升 |
| 🟡 中 | P2-2 错误消息信息泄露 | 30 min | 减少信息暴露 |
| 🟡 中 | P2-3 图譜扩展处理过量节点 | 30 min | 性能优化 + 缓解 DoS |
| 🟡 中 | P2-4 FTS 术语数量优化 | 15 min | 性能优化 |
| 🟢 低 | P3 系列问题 | 低 | 可在下次迭代处理 |

---

## 总结评分

| 维度 | 评分 (0-5) | 说明 |
|------|-----------|------|
| 输入验证 | 4.3 | Tokenization + 引用机制可靠，边界限制较完善 |
| 权限边界 | 4.0 | 大部分路径有多层防护，语义搜索是薄弱点 |
| 资源防护 | 3.6 | 深度/长度有限制，但数量型限制有缺失 |
| 旁路攻击防护 | 3.8 | 后过滤带来侧信道风险，需改进 |
| 错误处理 | 3.5 | 错误信息可能泄露内部结构 |
| 缓存安全 | 4.2 | 双重检查锁定在 Python 中足够安全 |

**综合评分: 4.1/5**

相比 v3.1 的 3.9/5 有小幅提升，核心的注入防护和基础权限边界已较稳固。主要薄弱点在于 DoS 防护的完备性（数量型限制不足）和语义搜索路径的权限过滤深度。建议优先修复 2 个 P1 问题，可在 1 小时内完成，修复后评分可提升至 4.4/5 左右。
