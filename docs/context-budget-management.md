# 上下文预算管理设计

> 创建时间：2026-02-27
> 状态：设计完成，待实现
> 前置依赖：Skill 保护 + 轮次识别（已合并）

## 1. 背景与问题

### 1.1 当前系统的上下文管理现状

系统通过 `MemoryManager` 实现了**轮间滑动窗口压缩**（保留最近 3 轮完整对话，压缩更早的轮次为摘要），并具备 Skill 注入保护和多 Skill 替换能力。

但存在以下结构性问题：

1. **工具结果无大小限制**：`core.py` 将 tool result 原封不动写入 `conversation_history`，一次 `Read` 大 CSV 可能产生数十 KB 甚至数 MB 的文本直接进入上下文
2. **压缩只管轮次不管体积**：`_super_compress` 以轮次数为滑动窗口，但 1 轮对话内可能包含 10 次工具调用，每次返回上万字符
3. **无 token 计数能力**：系统对自身上下文用量完全不知情，无法主动预警或弹性压缩
4. **成本不可控**：每次 LLM 调用发送完整 `system_prompt + conversation_history`，history 膨胀时每轮循环都在浪费 token

### 1.2 真实案例

一个 49 条记录的 CSV 文件（68.7KB），通过 `Read` 工具全量读取后，约 17,500 tokens 直接进入上下文，占 DeepSeek-chat 64K 上下文的 27%。

### 1.3 Claude Code 的参考实现

通过分析 Claude Code 的会话记录（JSONL）和 tool-results 文件，发现 CC 实现了 **persisted-output** 机制：

- 工具结果超过阈值时，完整输出存入磁盘文件
- 只将 ~2KB 预览（包裹在 `<persisted-output>` 标签中）写入 LLM 上下文
- LLM 如需更多细节，可通过 Read 工具分页读取持久化文件

## 2. 设计方案

### 2.1 两层防线架构

```
┌──────────────────────────────────────────────────┐
│              L1：轮内即时压缩                      │
│   工具结果写入 conversation_history 前的门卫        │
│   触发条件：单条 tool result > 8KB                 │
│   动作：存文件 + 只传预览                          │
└─────────────────────┬────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│              L2：轮间滑动窗口（现有逻辑增强）       │
│   新一轮对话开始时执行                             │
│   增强：token 预算感知 + 降级截断                  │
└──────────────────────────────────────────────────┘
```

### 2.2 L1：Persisted-Output 机制

#### 触发条件

所有工具的 tool result 统一适用 **8KB 阈值**（`PERSISTED_OUTPUT_THRESHOLD = 8192`）。

典型影响分布：

| 工具 | 典型返回大小 | 触发频率 |
|------|------------|---------|
| Read（大文件） | 几十 KB ~ 几 MB | 经常触发 |
| Bash（脚本输出） | 几百字节 ~ 30KB | 偶尔触发 |
| Write | 几十字节 | 不触发 |
| List | 几百字节 ~ 几 KB | 极少触发 |
| Skill 注入 | 走独立路径 | 不适用 |

#### 处理流程

```
tool 返回 result_str
    ↓
len(result_str) > 8KB ?
    ├── 否 → 正常写入 conversation_history
    └── 是 ↓
        写入文件：/workspace/.tool-results/{tool_call_id}.txt
            ↓
        替换 result_str 为预览格式：
        <persisted-output>
        Output too large ({size}KB). Full output saved to:
        .tool-results/{tool_call_id}.txt

        Preview (first 2KB):
        {result_str[:2048]}
        ...
        </persisted-output>
            ↓
        预览写入 conversation_history
```

#### 存储路径

```
/workspace/
├── uploads/
├── output/
├── skills/           （只读）
├── temp/
└── .tool-results/    （新增，系统管理）
    └── {tool_call_id}.txt
```

- 使用 `.` 前缀：List 工具已跳过 `.` 开头的文件，不会干扰 LLM 的目录探索
- 文件名用 `tool_call_id`：与 conversation_history 中的引用形成精确溯源链
- LLM 回读路径：`Read(".tool-results/{call_id}.txt", offset=X, limit=Y)`

#### 预览格式

预览大小：**2KB**（约 500 tokens），与 Claude Code 一致。

### 2.3 L2：轮间压缩增强

在现有 `_super_compress` 基础上增加两个能力：

#### 2.3.1 Token 预算感知

压缩后检查总 token 数，如果仍超预算，减少 `recent_conversation_rounds`：

```python
history = compress_history(conversation_history)
total_tokens = token_counter.count_messages(history)

while total_tokens > TOKEN_BUDGET and recent_rounds > 1:
    recent_rounds -= 1
    history = compress_with_rounds(conversation_history, recent_rounds)
    total_tokens = token_counter.count_messages(history)
```

#### 2.3.2 降级截断（兜底）

如果压缩到 1 轮仍超预算（极端场景），从最旧的非 system 消息开始逐条删除，并注入警告：

```
[系统提示] 由于上下文空间不足，部分早期对话已被移除。
如需引用这些内容，请重新提供。
```

### 2.4 Token 计数器

#### 选型

使用 `tiktoken` + `cl100k_base` 编码器 + **1.3x 安全系数**（覆盖中文文本偏差）。

理由：
- DeepSeek/GLM 没有公开的独立分词器包
- `tiktoken` 是 Rust C 扩展，微秒级性能，适合在热路径调用
- 预算管理不需要精确到个位数，量级正确即可
- 1.3x 系数保守覆盖中文文本（`cl100k_base` 对中文偏差约 10-20%）

#### 预算分配（以 DeepSeek-chat 64K 为例）

```
总上下文:  64K tokens
安全系数:  × 0.85 → 可用 ~54K tokens

分配：
├── 系统提示词:    ~2K （固定）
├── 工具定义:      ~2K （固定，5 个工具的 JSON Schema）
├── Skill 注入:    ~4K （固定，保护区）
├── 历史摘要:      ~3K （压缩后）
└── 工作区:        ~43K（当前轮 + 最近 2 轮完整对话）
```

## 3. 改动清单

| 文件 | 改动内容 | 复杂度 |
|------|---------|--------|
| `requirements-agent.txt` | 新增 `tiktoken` 依赖 | 低 |
| **新建** `agent_system/agent/token_counter.py` | Token 计数器封装（tiktoken + 安全系数） | 低 |
| `agent_system/agent/core.py` | L411 前插入 persisted-output 门卫逻辑 | 中 |
| `agent_system/agent/memory.py` | `compress_history` 增加 token 预算感知 + `emergency_truncate` | 中 |
| `agent_system/config.py` | 新增预算相关配置常量 | 低 |
| `docker-sandbox/server.py` | `.tool-results/` 目录自动创建（如果 persist 在沙盒内执行） | 低 |

## 4. 不做的事（明确排除）

- **Skill 卸载机制**：保持 Skill 永久驻留 + 多 Skill 替换逻辑不变
- **CSV 结构摘要**：预览中不额外追加文件统计信息，先跟 CC 行为一致
- **弹性预算分配**：不引入动态区域分配，用硬上限预算模型
- **LLM 侧 tokenize API**：不调用 Provider 的网络 API 做精确计数

## 5. 实现顺序

1. **Phase 1**：`token_counter.py` + `config.py` 常量 → 基础设施
2. **Phase 2**：`core.py` persisted-output 门卫 → L1 防线
3. **Phase 3**：`memory.py` 预算感知 + emergency_truncate → L2 增强
4. **Phase 4**：集成测试 + 真实 CSV 文件验证
