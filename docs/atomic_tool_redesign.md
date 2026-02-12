# 原子工具重构规划 - 最小通用基座

> 创建时间：2026-01-29
> 更新时间：2026-02-12
> 状态：Phase 1-4 全部完成（v0.14），158 个单元测试全部通过

## 1. 背景与目标

### 1.1 当前问题

1. **工具解耦不够**：`bash` 和 `run_python_code` 两个工具职责重叠

   - `bash` 可以执行 `python script.py`
   - `run_python_code` 提供有状态 REPL，但实际 Skill 未使用此特性
2. **LLM 不遵循 Skill 指令**：即使 SKILL.md 明确要求用 CLI 脚本，LLM 仍倾向于自己写代码
3. **审计留痕缺失**：`run_python_code` 的代码在内存中执行，无法追溯，不符合银行审计要求
4. **Web 模式容器泄漏**：TTLCache 过期时未调用 `cleanup()`，Docker 容器可能持续运行
5. **过度设计风险**：银行具体场景尚未明确，不应过早优化

### 1.2 目标

1. **最小通用基座**：先做最基础、扩展性最高的 Agent，避免过度优化
2. **审计友好**：所有执行的代码都有文件记录，便于追溯和审计
3. **强制执行策略**：移除 `run_python_code`，让 LLM 没有"直接传代码字符串"的选择
4. **统一沙箱边界**：所有文件操作都在 Docker 沙箱内通过 MCP 协议执行
5. **为未来预留**：Skill 作为扩展点，等银行接入后根据高频场景沉淀能力

### 1.3 设计原则

- **最小可用**：只做必要的工具，后续按需扩展
- **沙箱一致性**：所有需要在沙箱内执行的操作都做成 MCP 工具
- **审计留痕**：动态代码通过 Write + Bash 执行，代码文件可追溯
- **Skill 作为知识库**：Skill 提供领域知识和 CLI 脚本，不依赖 run_python_code

---

## 2. 架构设计

### 2.1 最小基座 v2

```
┌─────────────────────────────────────────────────────────────┐
│                    工具层 (Python)                           │
├─────────────────────────────────────────────────────────────┤
│ Read       │ Write      │ List       │ Bash    │ Skill     │
│ (读文件)   │ (写文件)   │ (列目录)   │ (执行)  │ (注入知识) │
├─────────────────────────────────────────────────────────────┤
│ render_chart │ render_table │ show_notification            │
│ (UI 工具，前端执行)                                         │
└─────────────────────────────────────────────────────────────┘
                              ↓ MCP 协议 (stdio)
┌─────────────────────────────────────────────────────────────┐
│                   Docker 沙箱 (server.py)                   │
├─────────────────────────────────────────────────────────────┤
│ Read      │ Write      │ List       │ Bash               │
│                                                            │
│ [保留但不暴露]: run_python / _GLOBAL_CONTEXT               │
└─────────────────────────────────────────────────────────────┘
                              ↓ 挂载
┌─────────────────────────────────────────────────────────────┐
│ /workspace/                                                │
│   ├── uploads/      (用户上传文件)                          │
│   ├── output/       (生成结果)                              │
│   ├── temp/         (临时脚本，会话结束清理，审计留痕)        │
│   └── skills/       (只读挂载，CLI 脚本)                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 工具清单

#### 核心工具（5个）

| 工具       | 类型 | 用途                                      |
| ---------- | ---- | ----------------------------------------- |
| `Read`     | MCP  | 读取任意文件（CSV、配置、Skill 文档等）   |
| `Write`    | MCP  | 写入文件（临时脚本、结果保存，审计留痕）  |
| `List`     | MCP  | 列出目录内容                              |
| `Bash`     | MCP  | 执行 Python 脚本（只允许 python/python3） |
| `Skill`    | 本地 | 注入领域知识到对话上下文                  |

> **命名规范（对齐 CC）**：全栈统一 PascalCase（`Read`/`Write`/`List`/`Bash`/`Skill`），
> 与 Claude Code 的 `Read`/`Write`/`Bash`/`Glob`/`Grep`/`Edit`/`Skill` 保持风格一致。
> Docker 端通过 `@mcp.tool(name="Read")` 覆盖，Python 函数名保持 snake_case（PEP 8 合规）。

#### UI 工具（3个，前端执行）

| 工具                  | 用途           |
| --------------------- | -------------- |
| `render_chart`      | 在前端渲染图表 |
| `render_table`      | 在前端渲染表格 |
| `show_notification` | 显示通知提示   |

#### 移除的工具

| 工具                | 移除原因                                                             |
| ------------------- | -------------------------------------------------------------------- |
| `run_python_code` | 代码在内存中无法留痕，不符合审计要求；LLM 倾向于自己写代码绕过 Skill |

#### 暂不添加的工具

| 工具             | 原因                                     |
| ---------------- | ---------------------------------------- |
| `Glob`         | 当前场景用 List 足够，后续按需添加       |
| `Grep`         | 当前场景不需要，后续按需添加             |
| `http_request` | 当前不需要联网，银行接入后按需添加       |
| `query_sql`    | 银行数据接入方式未定，后续按需添加       |

### 2.3 Bash 的定位

**核心用途**：

1. **执行 Skill CLI 脚本**：直接调用 skills 目录下的脚本
2. **执行临时脚本**：配合 Write 实现审计留痕

**白名单**：只允许 `python` 和 `python3`

**禁止**：

- `python -c "..."` - 禁止内联代码（绕过留痕）
- `python -m ...` - 禁止模块执行
- 其他任何命令

### 2.4 审计留痕机制

#### 场景1：执行已有 CLI 脚本

```
用户: "帮我计算每月定投3000，年化8%，10年后有多少钱"
    ↓
Agent: Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type aip --pmt 3000 --rate 0.08 --periods 120")
    ↓
审计记录: 调用了哪个脚本、什么参数、什么时间
```

#### 场景2：动态生成代码

```
用户: "分析这个CSV文件，找出异常值"
    ↓
Agent: Write("temp/analysis_20260129_001.py", code)
       Bash("python temp/analysis_20260129_001.py")
    ↓
审计记录: 代码文件 temp/analysis_20260129_001.py 可追溯
```

---

## 3. 分阶段实施计划

### Phase 1: MCP 工具层重构 (server.py) ✅ 已完成

**目标**：在 Docker 沙箱层新增原子工具
**状态**：已完成（2026-02-09），65 个单元测试全部通过

#### 1.1 MCP 工具签名（已实现）

```python
@mcp.tool(name="Read")      # PascalCase 对齐 CC，Python 函数名保持 PEP 8
def read_file(
    path: str,
    offset: int = 0,           # 起始行号（0-based），分页用
    limit: int = 2000,         # 最大读取行数，默认 2000
    encoding: str = "utf-8"    # utf-8 失败自动降级 gbk
) -> str:
    """
    读取文件内容（带分页和自动截断保护）。
    返回 JSON：{
        "success": bool,
        "content": str,          # 带行号（{line_no:6d}|{line_content}），单行超 2000 字符截断
        "encoding": str,         # 实际使用的编码（可能与传入不同）
        "lines_read": int,
        "total_lines": int,      # 高效统计（1MB chunk 计数）
        "truncated": bool,
        "error": str?
    }
    """

@mcp.tool(name="Write")
def write_file(
    path: str,
    content: str,
    encoding: str = "utf-8",
    append: bool = False
) -> str:
    """
    写入文件内容（审计留痕）。自动创建父目录。
    安全限制：禁止写入 skills/（只读），路径必须在 /workspace 内，内容不超过 1MB。
    返回 JSON：{
        "success": bool,
        "path": str,             # 相对于 /workspace 的路径
        "chars_written": int,    # 字符数（已修复，原名 bytes_written）
        "error": str?
    }
    """

@mcp.tool(name="List")
def list_files(
    path: str = ".",
    pattern: str = "*",
    recursive: bool = False,
    max_results: int = 500
) -> str:
    """
    列出目录内容。跳过隐藏文件。
    返回 JSON：{
        "success": bool,
        "files": [{"name": str, "type": "file"|"dir", "size": int}],
        "total_count": int,      # 实际匹配总数
        "truncated": bool,
        "error": str?
    }
    """
```

#### 1.2 安全与辅助函数（已实现）

```python
WORKSPACE = Path("/workspace")
READONLY_PATHS = [WORKSPACE / "skills"]
MAX_READ_LINES = 2000           # Read 默认行数上限
MAX_LINE_CHARS = 2000           # 单行字符截断阈值
MAX_WRITE_SIZE = 1_000_000      # Write 1MB 上限
MAX_OUTPUT_CHARS = 30000        # Bash 输出截断阈值
HEAD_RATIO = 0.8                # 截断时头部保留比例
MAX_LIST_RESULTS = 500          # List 条目上限

def _validate_path(path: str) -> Path:
    """路径安全校验（is_relative_to，注意 symlink 边界）"""
    target = (WORKSPACE / path).resolve()
    if not target.is_relative_to(WORKSPACE):
        raise ValueError(f"路径必须在 /workspace 内: {path}")
    return target

def _is_readonly(path: Path) -> bool:
    """只读区域检查"""
    return any(path.is_relative_to(ro) for ro in READONLY_PATHS)

def _count_lines(path: Path) -> int:
    """高效行数统计（1MB chunk 计数换行符，处理无尾换行边界）"""
    count = 0
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            count += chunk.count(b'\n')
    if count == 0:
        if path.stat().st_size > 0:
            count = 1
    else:
        with open(path, 'rb') as f:
            f.seek(-1, 2)
            if f.read(1) != b'\n':
                count += 1
    return count

def _truncate_output(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """输出截断（头 80% + 尾 20% 保留策略）"""
    if len(text) <= max_chars:
        return text
    head_size = int(max_chars * HEAD_RATIO)
    tail_size = max_chars - head_size
    return (
        text[:head_size]
        + f"\n\n...[输出被截断，共 {len(text)} 字符，保留头部 {head_size} + 尾部 {tail_size} 字符]...\n\n"
        + text[-tail_size:]
    )
```

#### 1.3 冻结的 REPL 工具（已实现）

```python
# ============================================================================
# [FROZEN] Python REPL 相关工具 - 当前不暴露给工具层
# 解冻条件：引入 PTC（Programmatic Tool Calling）机制后重新启用 @mcp.tool()
# 包含：run_python, reset_context, get_context_info
# ============================================================================

_GLOBAL_CONTEXT: Dict[str, Any] = {"__builtins__": __builtins__}
_EXECUTION_COUNT = 0

# @mcp.tool()  # [FROZEN] 审计留痕要求，改用 Write + Bash
def run_python(code: str) -> str: ...

# @mcp.tool()  # [FROZEN] 配套 run_python，一并冻结
def reset_context() -> str: ...

# @mcp.tool()  # [FROZEN] 配套 run_python，一并冻结
def get_context_info() -> str: ...
```

#### 1.4 Phase 1 实施注意事项（Review 补充）

> 以下内容基于对 Claude Code 原子工具设计的对比分析，以及对现有代码的审查。

##### 1.4.1 [高] Read 必须有上下文保护（参考 CC Read 工具）

**问题**：原方案 `max_lines: int = None` 默认无限制，Agent 不传参数时会读取整个文件。
100 万行 CSV 全读会导致 stdio 阻塞 + LLM 上下文爆炸。这与引入 Read 减少非必要上下文的初衷相矛盾。

**参考**：Claude Code 的 Read 工具采用三层保护：

1. **默认行数上限**：不传 limit 时最多读 2000 行
2. **单行字符截断**：超过 2000 字符的行自动截断
3. **offset + limit 分页**：Agent 可按需翻页读取大文件

**修正方案**：

```python
@mcp.tool(name="Read")
def read_file(
    path: str, 
    offset: int = 0,           # 起始行号（0-based）
    limit: int = 2000,         # 最大读取行数，默认 2000
    encoding: str = "utf-8"
) -> str:
    """
    读取文件内容（带自动截断保护）

    Args:
        path: 文件路径（相对于 /workspace）
        offset: 起始行号（0-based），用于分页读取大文件
        limit: 最大读取行数，默认 2000 行
        encoding: 文件编码，默认 utf-8

    Returns:
        JSON: {
            "success": bool,
            "content": str,          # 带行号的文件内容（cat -n 格式）
            "lines_read": int,       # 实际读取行数
            "total_lines": int,      # 文件总行数（快速统计）
            "truncated": bool,       # 是否被截断
            "error": str?
        }
    """
```

**关键设计点**：

- `total_lines` 告知 Agent 文件全貌，Agent 看到 `"total_lines": 85000, "lines_read": 2000, "truncated": true` 会自主决定翻页或写脚本
- `content` 采用带行号格式 `{line_no:6d}|{line_content}`（右对齐 6 位数字 + 竖线分隔），便于 Agent 定位和行号引用
- 单行超过 2000 字符时截断并追加 `...[truncated]` 标记

**性能注意**：`total_lines` 统计必须用高效方式，不能逐行 `readlines()`（百万行 CSV 会很慢）。使用 `rb` 模式按字节流统计：

```python
def _count_lines(path: Path) -> int:
    """高效统计文件行数（rb 模式，不加载全文到内存）"""
    with open(path, 'rb') as f:
        return sum(1 for _ in f)
```

##### 1.4.2 [高] 路径安全校验使用 is_relative_to()

**问题**：`str(target).startswith(str(WORKSPACE))` 存在前缀碰撞风险，`/workspace_evil` 也能通过检查。

**修正**：Docker 容器是 Python 3.11，直接用 `Path.is_relative_to()`（3.9+）：

```python
def _validate_path(path: str) -> Path:
    target = (WORKSPACE / path).resolve()
    if not target.is_relative_to(WORKSPACE):
        raise ValueError(f"Path must be within /workspace: {path}")
    return target
```

**边界说明**：`resolve()` 会解析 symlink。如果容器内存在指向 `/workspace` 外部的 symlink，理论上可绕过检查。当前 Docker `--network none` + skills 只读挂载的隔离度下风险极低，但实现时应在代码注释中标注此已知边界。

##### 1.4.3 [高] Write 自动创建父目录

**问题**：审计留痕场景 `Write("temp/analysis_001.py", code)` 会因 `/workspace/temp/` 不存在而报错。

**修正**：Write 内部自动 `path.parent.mkdir(parents=True, exist_ok=True)`。

**补充 — content 大小限制**：应加 `MAX_WRITE_SIZE = 1_000_000`（1MB）上限。LLM 理论上可能生成巨大字符串写入文件，超出限制时拒绝并提示。这也与审计留痕的"可追溯"要求一致——太大的文件不适合作为审计记录：

```python
MAX_WRITE_SIZE = 1_000_000  # 1MB

if len(content) > MAX_WRITE_SIZE:
    return json.dumps({
        "success": False,
        "error": f"内容过大（{len(content)} 字符），超过限制（{MAX_WRITE_SIZE} 字符）。请拆分写入。"
    })
```

##### 1.4.4 [高] Bash 输出截断保护（参考 CC Bash 工具）

**问题**：`Bash("python temp/analysis.py")` 如果脚本 print 了巨量数据，同样会撑爆上下文。

**参考**：Claude Code 的 Bash 工具在输出超过 30000 字符时自动截断。

**修正 — 头尾保留截断策略**：Python 脚本的错误信息和最终结果通常在输出末尾，仅保留头部会丢失最关键的信息。采用"头尾保留"策略（参考 CC 实现）：

```python
MAX_OUTPUT_CHARS = 30000
HEAD_RATIO = 0.8  # 头部保留 80%，尾部保留 20%

output = result.get("stdout", "")
if len(output) > MAX_OUTPUT_CHARS:
    head_size = int(MAX_OUTPUT_CHARS * HEAD_RATIO)
    tail_size = MAX_OUTPUT_CHARS - head_size
    output = (
        output[:head_size]
        + f"\n\n...[输出被截断，共 {len(output)} 字符，保留头部 {head_size} + 尾部 {tail_size} 字符]...\n\n"
        + output[-tail_size:]
    )
```

**分层实施**：
- **Phase 1（Docker 端 `Bash`）**：在 Bash 返回 JSON 前对 stdout 做截断，防止大量数据通过 stdio 管道传输时阻塞
- **Phase 2（Python 端 `BashTool.execute()`）**：在 `BashTool.execute()` 做二次截断，双保险，也可统一格式化截断提示信息

##### 1.4.5 [中] reset_context / get_context_info 一并处理

**问题**：规划只提到保留 `run_python`，但 `reset_context` 和 `get_context_info` 是其配套设施，也应一并处理。

**修正**：Phase 1 时注释掉这三个工具的 `@mcp.tool()` 装饰器，保留函数体，加统一注释：

```python
# ============================================================================
# [FROZEN] Python REPL 相关工具 - 当前不暴露给工具层
# 解冻条件：引入 PTC（Programmatic Tool Calling）机制后重新启用 @mcp.tool()
# 包含：run_python, reset_context, get_context_info
# ============================================================================

# @mcp.tool()
def run_python(code: str) -> str: ...
# @mcp.tool()
def reset_context() -> str: ...
# @mcp.tool()
def get_context_info() -> str: ...
```

##### 1.4.6 [中] 编码自动检测或友好报错

**问题**：银行场景的 CSV 极大概率是 GBK/GB18030 编码，默认 utf-8 会直接报错。

**方案**：Read 在 `utf-8` 解码失败时自动尝试 `gbk`，如仍失败则返回错误并提示可用编码：

```python
actual_encoding = encoding  # 跟踪实际使用的编码

try:
    content = path.read_text(encoding=encoding)
except UnicodeDecodeError:
    if encoding == "utf-8":
        # 自动降级尝试 gbk
        try:
            content = path.read_text(encoding="gbk")
            actual_encoding = "gbk"
        except UnicodeDecodeError:
            return {"success": False, "error": "编码识别失败，请尝试指定 encoding 参数（utf-8/gbk/gb18030/latin-1）"}
```

**关键**：返回 JSON 中必须包含 `encoding` 字段标注实际使用的编码，否则 Agent 后续 Write 时不知道该用什么编码回写，可能产生乱码：

```python
return json.dumps({
    "success": True,
    "content": content,
    "encoding": actual_encoding,  # ← 必须返回，告知 Agent 实际编码
    "lines_read": lines_read,
    "total_lines": total_lines,
    "truncated": truncated
})
```

##### 1.4.7 [中] List 返回结果数量限制

**问题**：`recursive=True` 且文件很多时返回的 JSON 会过大。

**修正**：加 `max_results: int = 500` 限制，超出时返回截断提示。返回中加 `total_count` 字段（实际匹配总数），让 Agent 知道被截断了多少，与 Read 的 `total_lines` / `truncated` 设计保持一致：

```python
return json.dumps({
    "success": True,
    "files": files[:max_results],
    "total_count": len(files),      # 实际匹配总数
    "truncated": len(files) > max_results
})
```

##### 1.4.8 [低] Bash 纵深防御（可选）

**问题**：安全白名单只在 Python 侧 `BashTool` 做，Docker 端 Bash 仍然完全开放（`shell=True` 无检查）。

**评估**：Docker 本身就是沙箱（`--network none`，资源限制），当前风险可接受。但如果未来有其他调用方绕过 `BashTool` 直接调 MCP，白名单就失效。

**建议**：Phase 1 暂不处理，在文档中标注为技术债，后续根据需要在 Bash 层也加白名单。

##### 1.4.9 [低] BashTool -c 检测增强

**问题**：`command.split()` 做分割在引号包裹等边缘场景可能被绕过。

**建议**：用 `shlex.split()` 代替 `str.split()` 做更健壮的命令解析。Phase 1 可选。

##### 1.5 Phase 1 Tech Debt（验收发现，Phase 2 或后续修复）

> 以下问题不阻塞 Phase 2 开始，但应在适当时机修复。

###### Tech Debt #1 [中] — Read 大文件双重全量 I/O ✅ 已修复

**问题**：原实现对每次调用做两次全文件扫描（`_count_lines()` + `readlines()` 全量加载）。

**修复**：改为单次 pass 逐行读取（跳过 offset → 收集 limit 行 → 继续计数 total_lines），内存只持有 limit 行。`_count_lines()` 辅助函数保留（供其他场景使用），但 Read 不再调用它。

###### Tech Debt #2 [低] — Write `bytes_written` 字段名语义不准确 ✅ 已修复

**问题**：`f.write(content)` 在文本模式下返回字符数，字段名 `bytes_written` 有误导性。

**修复**：字段名改为 `chars_written`。文档中的接口一致性表（2.4 节）已同步更新。

---

### Phase 2: 工具层适配 (mcp_tools.py + prompts.py) ✅ 已完成

**目标**：新增 Python 侧的工具类，移除 PythonTool，更新 System Prompt 完成路由-接口协同，统一全栈工具命名
**状态**：已完成（2026-02-09），52 个 Python 侧工具类测试 + 65 个 server.py 测试全部通过

**变更文件**：
- `docker-sandbox/server.py` — 补充 `@mcp.tool(name="...")` 覆盖（全栈命名统一）
- `agent_system/tools/mcp_tools.py` — 新增 MCPToolBase/ReadTool/WriteTool/ListTool，重写 BashTool，移除 PythonTool，更新工厂函数
- `agent_system/agent/prompts.py` — System Prompt 路由层重写（Tool usage policy + Doing tasks）
- `agent_system/tools/__init__.py` — 导出清理（移除 PythonTool，新增 MCPToolBase/ReadTool/WriteTool/ListTool）
- `server/copilot_adapter.py` — create_mcp_tools 调用点移除 output_dir 参数
- `tests/test_phase1_mcp_server_tools.py` → `tests/test_mcp_server_tools.py`（重命名 + Mock 兼容）
- `tests/test_mcp_tool_classes.py`（新增，52 个用例）

#### 2.0 Docker 端命名统一 (server.py)

> **前置步骤**：Phase 1 实现时使用了默认的 `@mcp.tool()` 装饰器，
> 工具名自动取自 Python 函数名（snake_case）。Phase 2 需要补充 `name` 参数覆盖，
> 使 MCP 协议层工具名与 LLM 可见名完全一致。

**变更**：

```python
# 变更前（Phase 1 已实现）
@mcp.tool()
def read_file(...): ...

@mcp.tool()
def write_file(...): ...

@mcp.tool()
def list_files(...): ...

@mcp.tool()
def exec_command(...): ...

# 变更后（Phase 2 补充 name 覆盖）
@mcp.tool(name="Read")
def read_file(...): ...

@mcp.tool(name="Write")
def write_file(...): ...

@mcp.tool(name="List")
def list_files(...): ...

@mcp.tool(name="Bash")
def exec_command(...): ...
```

> Python 函数名保持 snake_case（PEP 8），`name` 参数仅影响 MCP 协议暴露的工具名。
> `call_tool("Read", args)` 直接对应，无需翻译层。

**server.py 注释同步**：文件头部和常量区的旧工具名注释也需一并更新：

```python
# 变更前
"""
原子工具基座：read_file, write_file, list_files, exec_command
...
- v2.0: 新增 read_file/write_file/list_files，冻结 REPL 工具（Phase 1 重构）
"""
# read_file 保护
# write_file 保护
# exec_command 输出保护
# list_files 保护

# 变更后
"""
原子工具基座：Read, Write, List, Bash
...
- v2.0: 新增 Read/Write/List，冻结 REPL 工具（Phase 1 重构）
- v3.0: 全栈命名统一为 PascalCase（Phase 2）
"""
# Read 保护
# Write 保护
# Bash 输出保护
# List 保护
```

**测试同步**（已完成）：

1. **Mock 签名兼容**：`_MockFastMCP.tool()` 改为 `def tool(self, **kwargs):`，兼容 `@mcp.tool(name="Read")` 语法。
2. **测试文件重命名**：`test_phase1_mcp_server_tools.py` → `test_mcp_server_tools.py`。
3. **新增测试文件**：`test_mcp_tool_classes.py`（52 个用例，覆盖 ReadTool/WriteTool/ListTool/BashTool 的 Python 侧逻辑）。

#### 2.1 新增工具类（已实现）

> **设计原则（对齐 CC 工具体系）**：
> - **路由层**（System Prompt `# Tool usage policy`）：只说何时用哪个工具，不讲参数
> - **接口层**（工具 `description`）：只讲行为、约束和示例，不重复环境信息
> - **约束层**（工具 `parameters` JSON Schema）：类型、必填、枚举
> - **环境信息**只在 System Prompt `<env>` 块声明一次，工具 description 不重复

```python
# MCPToolBase 定义见 2.4 节
# ReadTool, WriteTool, ListTool 均继承 MCPToolBase，
# 共享 __init__(mcp_client) 和 _format_result(result)

class ReadTool(MCPToolBase):
    """读取文件工具"""
  
    @property
    def name(self) -> str:
        return "Read"
  
    @property
    def description(self) -> str:
        return """读取文件内容（带分页和自动截断保护）。

默认从文件开头读取最多 2000 行。超过 2000 字符的行自动截断。
返回包含 total_lines 和 truncated 字段，可据此决定翻页或改用脚本处理。

示例：
- Read("uploads/data.csv")
- Read("uploads/big.csv", offset=2000, limit=2000)  # 分页
- Read("skills/fin-advisor-math/SKILL.md")
"""
  
    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对于 /workspace）"
                },
                "offset": {
                    "type": "integer",
                    "description": "起始行号（0-based），用于分页读取大文件"
                },
                "limit": {
                    "type": "integer",
                    "description": "最大读取行数，默认 2000"
                }
            },
            "required": ["path"]
        }
  
    def execute(self, path: str, offset: int = 0, limit: int = 2000) -> str:
        args = {"path": path, "offset": offset, "limit": limit}
        result = self.client.call_tool("Read", args)
        return self._format_result(result)


class WriteTool(MCPToolBase):
    """写入文件工具"""
  
    @property
    def name(self) -> str:
        return "Write"
  
    @property
    def description(self) -> str:
        return """写入文件内容（审计留痕）。自动创建父目录。

限制：禁止写入 skills/ 目录（只读），内容不超过 1MB。

示例：
- Write("temp/analysis_001.py", code)  # 临时脚本，配合 Bash 执行
- Write("output/result.json", json_str)
"""
  
    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对于 /workspace）"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                },
                "append": {
                    "type": "boolean",
                    "description": "是否追加模式，默认覆盖"
                }
            },
            "required": ["path", "content"]
        }
  
    def execute(self, path: str, content: str, append: bool = False) -> str:
        args = {"path": path, "content": content, "append": append}
        result = self.client.call_tool("Write", args)
        return self._format_result(result)


class ListTool(MCPToolBase):
    """列出目录工具"""
  
    @property
    def name(self) -> str:
        return "List"
  
    @property
    def description(self) -> str:
        return """列出目录内容。返回文件名、类型和大小。

结果超过 500 条时自动截断，返回 total_count 和 truncated 字段。

示例：
- List("uploads/")
- List(".", pattern="*.csv")
- List("skills/", recursive=True)
"""
  
    @property
    def parameters(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径（相对于 /workspace），默认当前目录"
                },
                "pattern": {
                    "type": "string",
                    "description": "文件名模式（glob 语法，如 *.csv），默认 *"
                },
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归子目录，默认 false"
                }
            },
            "required": []
        }
  
    def execute(self, path: str = ".", pattern: str = "*", recursive: bool = False) -> str:
        args = {"path": path, "pattern": pattern, "recursive": recursive}
        result = self.client.call_tool("List", args)
        return self._format_result(result)
```

#### 2.2 移除 PythonTool（已实现）

移除 `PythonTool` 类及其 import。工厂函数 `create_mcp_tools()` 的完整变更见 2.7 节。

#### 2.3 精简 BashTool 白名单（已实现）

> **变更点**（对照当前代码 `mcp_tools.py:290-377`）：
> 1. `name` 从 `"bash"` → `"Bash"`（PascalCase 统一）
> 2. `call_tool("exec_command", ...)` → `call_tool("Bash", ...)`（与 server.py 的 `@mcp.tool(name="Bash")` 对应）
> 3. 白名单从 12 个命令缩减为 `python/python3`（文件操作已由原子工具覆盖）
> 4. description 增加**反向路由**（告知 LLM 文件操作应使用专用工具），与 system prompt 正向路由形成闭合
> 5. `str.split()` 改为 `shlex.split()` 防止引号路径解析错误
> 6. 保留危险字符检查（管道、重定向、连接符注入防护）
> 7. 增加输出二次截断保护（Phase 1 Docker 端已截断，此处双保险）
>
> **mcp_tools.py 模块头注释**也需同步更新：
> ```python
> # 变更前
> """
> 包含：
> - BashTool: bash 命令执行 (对应 server.py 的 exec_command)
> - PythonTool: Python 代码执行 (对应 server.py 的 run_python)
> """
>
> # 变更后
> """
> 包含：
> - BashTool: 执行 Python 脚本 (MCP 工具名: Bash)
> - ReadTool: 读取文件 (MCP 工具名: Read)
> - WriteTool: 写入文件 (MCP 工具名: Write)
> - ListTool: 列出目录 (MCP 工具名: List)
> """
> ```

```python
import shlex

# 输出截断常量（与 Docker 端保持一致）
MAX_OUTPUT_CHARS = 30000
HEAD_RATIO = 0.8

class BashTool(BaseTool):
    """Bash 命令执行工具"""
  
    ALLOWED_COMMANDS = {'python', 'python3'}
    DANGEROUS_PATTERNS = ['>', '>>', '|', ';', '&&', '||', '`', '$(', 'rm ', 'mv ']
  
    def __init__(self, mcp_client: MCPClient):
        self.client = mcp_client
  
    @property
    def name(self) -> str:
        return "Bash"
  
    @property
    def description(self) -> str:
        return """执行 Python 脚本。仅允许 python/python3 命令。

重要：不要将此工具用于文件操作，请使用专用工具：
- 读取文件 → Read
- 写入文件 → Write
- 列出目录 → List

用法：
1. 执行 Skill CLI 脚本（推荐）：
   Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type aip --pmt 3000")
2. 执行临时脚本（配合 Write，审计留痕）：
   Bash("python temp/my_script.py")

禁止：python -c（内联代码）和 python -m（模块执行）。
"""
  
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令（仅限 python/python3 + .py 文件）"
                }
            },
            "required": ["command"]
        }
  
    def execute(self, command: str) -> str:
        command = command.strip()
        if not command:
            return "Error: Empty command"
      
        # 危险字符检查（注入防护，在 shlex 解析前拦截）
        if any(p in command for p in self.DANGEROUS_PATTERNS):
            return "Error: Forbidden characters in command"
      
        # 使用 shlex.split() 正确处理引号路径
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return f"Error: Invalid command syntax: {e}"
      
        base_cmd = parts[0]
        if base_cmd not in self.ALLOWED_COMMANDS:
            return f"Error: Only python/python3 allowed, got '{base_cmd}'"
      
        # 禁止 -c 和 -m
        if len(parts) >= 2 and parts[1] in ('-c', '-m'):
            return "Error: python -c and -m are forbidden. Use Write + Bash for audit trail."
      
        # 必须执行 .py 文件
        if len(parts) >= 2 and not parts[1].endswith('.py'):
            return "Error: Must execute a .py script file"
      
        # 调用 MCP
        try:
            result = self.client.call_tool("Bash", {"command": command})
        except Exception as e:
            return f"Error: {e}"
      
        # 格式化输出（含二次截断保护）
        return self._format_exec_result(result)
  
    def _format_exec_result(self, result: Dict[str, Any]) -> str:
        """格式化 Bash 返回结果（含输出截断）"""
        output = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", 0)
      
        # 二次截断保护（Docker 端已做一次，此处双保险）
        if len(output) > MAX_OUTPUT_CHARS:
            head = int(MAX_OUTPUT_CHARS * HEAD_RATIO)
            tail = MAX_OUTPUT_CHARS - head
            output = (
                output[:head]
                + f"\n\n...[输出被截断，共 {len(output)} 字符]...\n\n"
                + output[-tail:]
            )
      
        if stderr:
            output += f"\n[stderr]: {stderr}"
        if exit_code != 0:
            output += f"\n[exit_code]: {exit_code}"
      
        return output or "[No output]"
```

#### 2.4 `_format_result()` 公共方法（已实现）

> **背景**：Read/Write/List 返回 `{"success": bool, ...}` 格式，
> 而 Bash 返回 `{"status": str, "exit_code": int, "stdout": str, "stderr": str}`。
> `ReadTool`、`WriteTool`、`ListTool` 需要统一的结果格式化方法。
> `BashTool` 使用独立的 `_format_exec_result()` 处理旧格式（见 2.3 节），不走此方法。

**方案**：在 `mcp_tools.py` 中定义基类或辅助函数（不污染 `base.py`，因为这是 MCP 工具特有的适配逻辑）：

```python
class MCPToolBase(BaseTool):
    """MCP 原子工具基类（Read/Write/List 共用）"""
  
    def __init__(self, mcp_client: MCPClient):
        self.client = mcp_client
  
    def _format_result(self, result: Dict[str, Any]) -> str:
        """
        格式化 Read/Write/List 的返回结果。

        这些工具统一返回 {"success": bool, ...} 格式。
        成功时：提取核心内容返回给 LLM（不含冗余的 success 字段）。
        失败时：返回 error 信息。

        注意：BashTool 返回格式不同，不走此方法。
        """
        if not result.get("success", False):
            return f"Error: {result.get('error', 'Unknown error')}"
        # 成功时，将完整 JSON 返回给 LLM（保留 total_lines/truncated 等元数据）
        # LLM 需要这些信息决定后续操作（翻页、改用脚本等）
        return json.dumps(result, ensure_ascii=False)
```

**继承关系**：`ReadTool(MCPToolBase)`, `WriteTool(MCPToolBase)`, `ListTool(MCPToolBase)`，
各子类不再需要 `__init__` 和 `_format_result()`，只需定义 `name`、`description`、`parameters`、`execute`。
`BashTool` 继承 `BaseTool`（非 MCPToolBase），因为 Bash 返回格式不同。

**设计决策：成功时返回完整 JSON 而非纯文本**

`_format_result()` 成功时返回 `json.dumps(result)`（完整 JSON），**不**提取 `content` 纯文本返回。理由：
1. **LLM 需要元数据做决策**：`total_lines`/`truncated` 帮助 LLM 判断是否翻页；`encoding` 帮助后续 Write 保持一致编码
2. **与 CC 行为对齐**：CC 的 Read/Write/Bash 返回均包含结构化元数据，LLM 已被训练理解此格式
3. **统一异常处理**：失败时返回 `"Error: ..."` 纯文本，成功时返回 JSON——两种格式 LLM 可轻松区分

如果后续发现 JSON 包装导致 token 浪费（尤其 Read 的 `content` 已很长），可考虑仅对 Read 做特殊处理（只返回 content + 尾部元数据注释），但初版先保持统一。

#### 2.5 跨 Phase 接口一致性参考

| MCP 工具 | 返回格式 | Python 侧适配 |
|----------|---------|---------------|
| `Read` | `{"success": bool, "content": str, "encoding": str, "lines_read": int, "total_lines": int, "truncated": bool, "error": str?}` | `MCPToolBase._format_result()` |
| `Write` | `{"success": bool, "path": str, "chars_written": int, "error": str?}` | `MCPToolBase._format_result()` |
| `List` | `{"success": bool, "files": [...], "total_count": int, "truncated": bool, "error": str?}` | `MCPToolBase._format_result()` |
| `Bash` | `{"status": str, "exit_code": int, "stdout": str, "stderr": str}` | `BashTool._format_exec_result()` |

#### 2.6 System Prompt 更新 (prompts.py)（已实现）

> **设计原则（对齐 CC 工具体系 `# Tool usage policy`）**：
>
> CC 的 system prompt 与工具 description 遵循严格的分层协同：
> - **System Prompt 路由层**：只说「何时用哪个工具」，不讲参数细节
> - **Tool Description 接口层**：只说「怎么用、约束、示例」，不重复环境信息
> - **两者互为补充、不互相重复**
>
> 此外，CC 的 Bash description 包含**反向路由**（"不要用 Bash 做文件操作"），
> 与 system prompt 的正向路由形成闭合回路。Phase 2 的 BashTool description（2.3 节）
> 已包含此反向路由，此处 system prompt 提供正向路由。

##### 2.6.1 需要修改的区域

**`# Tool usage policy` 区域（重写）**：

当前版本（需删除）：
```
- Use specialized tools instead of bash commands when possible. For example, use run_python_code for Python execution rather than bash python commands.
```

替换为（正向路由 + 审计留痕模式引导）：
```
- Use specialized tools instead of Bash commands. For file operations, use dedicated tools: Read for reading files, Write for creating/writing files, and List for listing directory contents.
- Bash is restricted to executing Python scripts only (python/python3). It cannot be used for file exploration or other shell commands.
- When you need to run custom analysis code, use the Write + Bash pattern for audit trail:
  1. Write("temp/analysis_001.py", code)
  2. Bash("python temp/analysis_001.py")
  All executed code must have a file on disk for traceability.
```

**`# Doing tasks` 区域（补充）**：

在现有内容后追加：
```
- Before operating on any file, use Read to understand its content first. Never assume file structure or content without reading.
```

**环境信息 `<env>` 块（保持不变）**：

```
<env>
Working directory: /workspace/
User files: /workspace/uploads/{detected_files}
Output directory: /workspace/output/
Skills directory: /workspace/skills/
</env>
```

`<env>` 块是所有路径信息的唯一来源。工具 description 不再重复这些路径。

##### 2.6.2 完整的 `# Tool usage policy` 重写

```python
# Tool usage policy 完整内容（替换 prompts.py 中对应区域）

"""
# Tool usage policy
- You should proactively use the Skill tool when the task at hand matches a skill's description.
- /<skill-name> (e.g., /csv-data-summarizer) is shorthand for users to invoke a skill. When executed, use the Skill tool to load it. IMPORTANT: Only use Skill for skills listed in its Available skills section - do not guess.
- You can call multiple tools in a single response. If you intend to call multiple tools and there are no dependencies between them, make all independent tool calls in parallel. Maximize use of parallel tool calls where possible to increase efficiency. However, if some tool calls depend on previous calls to inform dependent values, do NOT call these tools in parallel and instead call them sequentially.
- Use specialized tools instead of Bash commands. For file operations, use dedicated tools: Read for reading files, Write for creating/writing files, and List for listing directory contents.
- Bash is restricted to executing Python scripts only (python/python3). It cannot be used for file exploration or other shell commands.
- When you need to run custom analysis code, use the Write + Bash pattern for audit trail:
  1. Write("temp/analysis_001.py", code)
  2. Bash("python temp/analysis_001.py")
  All executed code must have a file on disk for traceability.
- When presenting results to users, prefer using UI tools (render_chart, render_table, show_notification) over plain text output for structured data.
"""
```

##### 2.6.3 路由-接口协同验证表

验证每个工具在 system prompt（路由层）和 tool description（接口层）的职责不重叠、不遗漏：

| 工具 | System Prompt 路由 | Tool Description 接口 | 闭合状态 |
|------|-------------------|----------------------|---------|
| `Read` | "use Read for reading files"（正向路由） | 行为：分页、截断保护、total_lines；示例 | ✅ 闭合 |
| `Write` | "use Write for creating/writing files"（正向路由）+ "Write + Bash pattern"（工作流） | 行为：审计留痕、自动建目录；约束：只读区域、1MB 限制；示例 | ✅ 闭合 |
| `List` | "use List for listing directory contents"（正向路由） | 行为：截断保护、total_count；示例 | ✅ 闭合 |
| `Bash` | "restricted to executing Python scripts only"（正向约束）+ "Write + Bash pattern"（工作流） | **反向路由**："不要用此工具做文件操作，用 Read/Write/List"；约束：仅 python/python3；示例 | ✅ 双向闭合 |
| `Skill` | "proactively use the Skill tool"（正向路由） | Available skills 列表；调用方式 | ✅ 闭合 |
| UI 工具 | "prefer using UI tools for structured data"（正向路由） | 各自参数定义 | ✅ 闭合 |

#### 2.7 工厂函数清理 (create_mcp_tools)（已实现）

> 移除 PythonTool 后，`output_dir` 参数及相关逻辑不再需要。

**变更前**：
```python
def create_mcp_tools(
    session_id: str = None,
    uploads_dir: str = None,
    output_dir: str = None         # ← PythonTool 专用，需移除
) -> List[BaseTool]:
    # ...
    output_path = workspace_path / "output"
    output_path.mkdir(parents=True, exist_ok=True)

    tools = [
        BashTool(mcp_client),
        PythonTool(mcp_client, output_dir=output_path)
    ]
```

**变更后**：
```python
def create_mcp_tools(
    session_id: str = None,
    uploads_dir: str = None,
) -> List[BaseTool]:
    """
    创建 MCP 工具集（Bash, Read, Write, List）
    PythonTool 已移除 — 改用 Write + Bash，便于审计留痕
    """
    # ... workspace_path 逻辑不变 ...

    mcp_client = MCPClient(
        session_id=session_id,
        workspace_path=workspace_path,
        skills_path=Config.SKILLS_DIR
    )

    tools = [
        BashTool(mcp_client),
        ReadTool(mcp_client),
        WriteTool(mcp_client),
        ListTool(mcp_client),
    ]
    return tools
```

##### 调用点变更清单

**1. `server/copilot_adapter.py` — L195-198**（主调用点）

变更前：
```python
# 注册 MCP 工具（bash, run_python_code）
mcp_tools = create_mcp_tools(
    uploads_dir=str(uploads_dir),
    output_dir=str(output_dir)
)
```

变更后：
```python
# 注册 MCP 工具（Bash, Read, Write, List）
mcp_tools = create_mcp_tools(
    uploads_dir=str(uploads_dir),
)
```

注意：`output_dir` 变量在此函数上下文中可能还有其它用途（如 session 目录结构），
删除参数传入即可，不要连 `output_dir` 的定义一起删除，需逐行确认。

**2. `agent_system/tools/__init__.py` — L11-16, L30-33**（导出清理）

变更前：
```python
from .mcp_tools import (
    MCPClient,
    BashTool,
    PythonTool,
    create_mcp_tools,
)
# ...
__all__ = [
    # ...
    "BashTool",
    "PythonTool",
    "create_mcp_tools",
]
```

变更后：
```python
from .mcp_tools import (
    MCPClient,
    MCPToolBase,
    BashTool,
    ReadTool,
    WriteTool,
    ListTool,
    create_mcp_tools,
)
# ...
__all__ = [
    # ...
    "MCPToolBase",
    "BashTool",
    "ReadTool",
    "WriteTool",
    "ListTool",
    "create_mcp_tools",
]
```

移除 `PythonTool` 导出，新增 `MCPToolBase`/`ReadTool`/`WriteTool`/`ListTool`。

**3. `server/app.py`**（需确认）

当前 `server/app.py` 未直接调用 `create_mcp_tools()`，但 Phase 2 应确认无新增调用。

---

### Phase 3: Web 模式容器泄漏修复 + MCPClient 引用规范化 ✅ 已完成

**目标**：确保 Agent 过期时正确清理 Docker 容器；规范化 MCPClient 的引用获取方式
**状态**：已完成（2026-02-12），7 个新增单元测试全部通过
**实际工作量**：约 1.5h

#### 3.0 问题分析

**问题 1 — 容器泄漏**：`TTLCache` 过期时仅移除缓存条目，不触发任何清理回调。
过期的 `AgentCacheEntry` 被 GC 回收后，其内部的 Docker 容器可能仍在运行。

**问题 2 — MCPClient 引用链路不规范**：`create_mcp_tools()` 只返回工具列表，
`MCPClient` 实例是工厂函数内部的局部变量，外部无法直接获取引用。
当前 `main.py` L117-118 有一个 hack：`agent._mcp_client = mcp_tools[0].client`，
直接访问工具的内部属性，耦合了实现细节。

**问题 3 — TTLCache 懒惰驱逐**：`cachetools.TTLCache` 不会主动驱逐过期条目，
仅在访问缓存时（get/set/contains/iterate）才触发过期检查。如果长时间无请求，
过期容器会一直运行。

**方案**（方案 B）：
1. `create_mcp_tools()` 返回 `(List[BaseTool], MCPClient)` 元组
2. `AgentCacheEntry` 增加 `mcp_client` 字段，显式持有引用
3. 自定义 `CleanupTTLCache`，在 `__delitem__` 中触发清理回调
4. 后台定时器线程，定期触发 `TTLCache.expire()` 主动驱逐过期条目

**变更文件**：
- `agent_system/tools/mcp_tools.py` — `create_mcp_tools()` 返回值变更
- `server/copilot_adapter.py` — 核心改造（CleanupTTLCache、AgentCacheEntry、清理回调、定时器）
- `agent_system/main.py` — 适配新返回值，移除 hack
- `tests/test_mcp_tool_classes.py` — 更新工厂函数测试

#### 3.1 `create_mcp_tools()` 返回值变更 (mcp_tools.py)

> **核心变更**：返回类型从 `List[BaseTool]` 改为 `Tuple[List[BaseTool], MCPClient]`，
> 让调用方可以显式获取 MCPClient 引用，用于生命周期管理。

**变更前**（当前代码 `mcp_tools.py:596-642`）：

```python
def create_mcp_tools(
    session_id: str = None,
    uploads_dir: str = None,
) -> List[BaseTool]:
    """
    创建 MCP 工具集（Bash, Read, Write, List）
    PythonTool 已移除 — 改用 Write + Bash，便于审计留痕
    """
    # ... workspace_path 逻辑不变 ...

    mcp_client = MCPClient(
        session_id=session_id,
        workspace_path=workspace_path,
        skills_path=Config.SKILLS_DIR
    )

    tools = [
        BashTool(mcp_client),
        ReadTool(mcp_client),
        WriteTool(mcp_client),
        ListTool(mcp_client),
    ]

    return tools
```

**变更后**：

```python
from typing import Tuple

def create_mcp_tools(
    session_id: str = None,
    uploads_dir: str = None,
) -> Tuple[List[BaseTool], MCPClient]:
    """
    创建 MCP 工具集（Bash, Read, Write, List）及其共享的 MCPClient。
    PythonTool 已移除 — 改用 Write + Bash，便于审计留痕。

    Returns:
        (tools, mcp_client) 元组。调用方应保存 mcp_client 引用用于生命周期管理。
    """
    # ... workspace_path 逻辑不变（L612-L631 完全保留）...

    mcp_client = MCPClient(
        session_id=session_id,
        workspace_path=workspace_path,
        skills_path=Config.SKILLS_DIR
    )

    tools = [
        BashTool(mcp_client),
        ReadTool(mcp_client),
        WriteTool(mcp_client),
        ListTool(mcp_client),
    ]

    return tools, mcp_client
```

**关键点**：
- 只改返回语句：`return tools` → `return tools, mcp_client`
- 函数签名增加 `-> Tuple[List[BaseTool], MCPClient]` 类型标注
- import 区域增加 `from typing import Tuple`（如果尚未导入）
- docstring 更新说明返回元组
- 函数内部逻辑（workspace_path 推导、session_id 推导）**完全不变**

#### 3.2 CleanupTTLCache 自定义缓存类 (copilot_adapter.py)

> **依赖版本**：`cachetools>=5.3.0`（当前安装 6.2.4），`TTLCache` 继承链：
> `TTLCache -> TLRUCache -> Cache -> MutableMapping`。
> `__delitem__` 在条目被移除时调用（包括 TTL 过期驱逐和手动删除）。

在 `copilot_adapter.py` 的 `# 数据模型` 区域前面新增：

```python
from cachetools import TTLCache


class CleanupTTLCache(TTLCache):
    """
    支持过期回调的 TTL 缓存。
    
    在条目被移除时（TTL 过期驱逐 或 手动 del）触发 on_expire 回调。
    回调签名：on_expire(key: str, value: Any) -> None
    """

    def __init__(self, maxsize, ttl, on_expire=None):
        super().__init__(maxsize, ttl)
        self._on_expire = on_expire

    def __delitem__(self, key):
        # 先取出 value（必须在 super().__delitem__ 之前，否则删除后取不到）
        # 使用 Cache.__getitem__ 绕过 TTLCache 的过期检查，避免递归驱逐
        value = None
        try:
            value = Cache.__getitem__(self, key)
        except KeyError:
            pass

        # 执行实际删除
        super().__delitem__(key)

        # 删除成功后触发回调（在删除之后执行，避免回调异常阻塞删除）
        if self._on_expire and value is not None:
            try:
                self._on_expire(key, value)
            except Exception as e:
                print(f"[CleanupTTLCache] Cleanup error for {key}: {e}")
```

**⚠️ 实施注意事项**：

1. **import `Cache`**：需要 `from cachetools import TTLCache, Cache`（`Cache` 是 TTLCache 的祖父类）
2. **为什么用 `Cache.__getitem__`**：直接 `self[key]` 会触发 TTLCache 的 `__getitem__`，
   后者内部会调用 `expire()` 驱逐其他过期条目 → 递归调用 `__delitem__` → 可能导致不可预测行为。
   `Cache.__getitem__` 跳过 TTL 过期检查，直接从底层字典取值。
3. **回调在删除之后执行**：确保即使回调抛异常，缓存条目也已被正确移除。
4. **死锁防护**：`_cleanup_agent` 回调中**绝对不能获取 `self._cache_lock`**，
   因为调用链是 `with _cache_lock → cache[key] = value → 驱逐旧条目 → __delitem__ → _cleanup_agent`，
   锁已经被外层 `_get_or_create_agent` 持有。回调中只做 I/O 操作（停容器、删文件），不操作缓存。

#### 3.3 AgentCacheEntry 扩展 (copilot_adapter.py)

**变更前**（当前代码 `copilot_adapter.py:59-69`）：

```python
@dataclass
class AgentCacheEntry:
    """Agent 缓存条目"""
    agent: Agent
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    
    def touch(self):
        """更新最后访问时间"""
        self.last_access = time.time()
```

**变更后**：

```python
@dataclass
class AgentCacheEntry:
    """Agent 缓存条目"""
    agent: Agent
    session_id: str
    mcp_client: Optional['MCPClient'] = None  # Phase 3: 显式持有 MCPClient 引用
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    
    def touch(self):
        """更新最后访问时间"""
        self.last_access = time.time()
```

**关键点**：
- `mcp_client` 使用 `Optional` + 字符串前向引用 `'MCPClient'`，因为 `MCPClient` 从 `agent_system.tools` 导入
- 需要在文件顶部 import 区域确认已有：`from agent_system.tools import ..., MCPClient`
  （当前 L28 只有 `ToolRegistry, register_ui_tools, create_mcp_tools`，**需新增 `MCPClient`**）

import 变更（`copilot_adapter.py` L28）：

```python
# 变更前
from agent_system.tools import ToolRegistry, register_ui_tools, create_mcp_tools

# 变更后
from agent_system.tools import ToolRegistry, register_ui_tools, create_mcp_tools, MCPClient
```

#### 3.4 CopilotBackend 改造 (copilot_adapter.py)

##### 3.4.1 `__init__` — 使用 CleanupTTLCache + 启动定时器

**变更前**（`copilot_adapter.py:98-130`）：

```python
def __init__(
    self,
    max_agents: int = 100,
    ttl_seconds: int = 1800,
    default_timeout: float = 600.0
):
    self.max_agents = max_agents
    self.ttl_seconds = ttl_seconds
    self.default_timeout = default_timeout
    
    # Agent 缓存（使用 TTLCache 自动过期）
    self._agent_cache: TTLCache[str, AgentCacheEntry] = TTLCache(
        maxsize=max_agents,
        ttl=ttl_seconds
    )
    self._cache_lock = Lock()
    
    # 统计信息
    self._stats = {
        "total_requests": 0,
        "active_sessions": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "errors": 0
    }
```

**变更后**：

```python
def __init__(
    self,
    max_agents: int = 100,
    ttl_seconds: int = 1800,
    default_timeout: float = 600.0,
    cleanup_interval: int = 60  # Phase 3: 过期检查间隔（秒）
):
    self.max_agents = max_agents
    self.ttl_seconds = ttl_seconds
    self.default_timeout = default_timeout
    
    # Agent 缓存（Phase 3: 使用 CleanupTTLCache，过期时自动清理容器）
    self._agent_cache: CleanupTTLCache = CleanupTTLCache(
        maxsize=max_agents,
        ttl=ttl_seconds,
        on_expire=self._cleanup_agent
    )
    self._cache_lock = Lock()
    
    # 统计信息
    self._stats = {
        "total_requests": 0,
        "active_sessions": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "errors": 0
    }
    
    # Phase 3: 启动后台定时清理线程（解决 TTLCache 懒惰驱逐问题）
    self._start_cleanup_timer(cleanup_interval)
```

**注意**：移除文件顶部原有的 `from cachetools import TTLCache`（L21），
因为 `CleanupTTLCache` 已经在同文件中定义，且它内部已经 import 了 `TTLCache`。
或者保留 import 但改为 `from cachetools import TTLCache, Cache`（`CleanupTTLCache` 需要 `Cache`）。

推荐做法——import 区域改为：

```python
# 变更前
from cachetools import TTLCache

# 变更后
from cachetools import TTLCache, Cache
```

`CleanupTTLCache` 类定义中使用 `Cache.__getitem__`（见 3.2 节）。

##### 3.4.2 `_start_cleanup_timer` — 后台定时器

在 `CopilotBackend` 类中新增方法（放在 `__init__` 之后）：

```python
def _start_cleanup_timer(self, interval: int):
    """
    启动后台定时清理线程。
    
    TTLCache 是懒惰驱逐——仅在访问时触发过期检查。
    此定时器定期调用 expire() 主动清理过期条目，确保容器及时释放。
    
    Args:
        interval: 检查间隔（秒），默认 60
    """
    import threading
    
    def _periodic_expire():
        while True:
            time.sleep(interval)
            try:
                with self._cache_lock:
                    # expire() 触发 TTLCache 内部的过期检查
                    # 过期条目会被 __delitem__ 移除，进而触发 _cleanup_agent 回调
                    self._agent_cache.expire()
            except Exception as e:
                print(f"[CopilotBackend] Periodic cleanup error: {e}")
    
    t = threading.Thread(target=_periodic_expire, daemon=True, name="cache-cleanup")
    t.start()
```

**关键点**：
- `daemon=True`：主进程退出时线程自动终止，不会阻塞关闭
- `expire()` 是 `cachetools.TTLCache` 的公开方法（5.x+ 可用，当前 6.2.4 支持）
- `expire()` 内部会对过期条目调用 `__delitem__`，进而触发 `_cleanup_agent`
- 此处**必须持有 `_cache_lock`**，因为 `expire()` 修改缓存数据结构
- `_cleanup_agent` 回调在锁内执行（由 `expire() → __delitem__` 触发），
  所以回调内部**不能再获取锁**（见 3.2 节注意事项 #4）

##### 3.4.3 `_create_agent` — 适配新返回值

**变更前**（`copilot_adapter.py:168-209`）：

```python
def _create_agent(self, session_id: str) -> Agent:
    """创建新的 Agent 实例"""
    # ...（L179-191 不变）...
    
    # 注册 MCP 工具（Bash, Read, Write, List）
    mcp_tools = create_mcp_tools(
        uploads_dir=str(uploads_dir),
    )
    for tool in mcp_tools:
        tool_registry.register(tool)
    
    # 创建 Agent
    agent = Agent(
        skill_manager=skill_manager,
        tool_registry=tool_registry,
        log_file=str(log_file),
        uploads_dir=str(uploads_dir)
    )
    
    return agent
```

**变更后**：

```python
def _create_agent(self, session_id: str) -> tuple:
    """
    创建新的 Agent 实例
    
    Returns:
        (agent, mcp_client) 元组
    """
    # ...（L179-191 不变：ensure_session_dirs, skill_manager, tool_registry, skill_tool, ui_tools）...
    
    # 注册 MCP 工具（Bash, Read, Write, List）
    mcp_tools, mcp_client = create_mcp_tools(
        uploads_dir=str(uploads_dir),
    )
    for tool in mcp_tools:
        tool_registry.register(tool)
    
    # 创建 Agent
    agent = Agent(
        skill_manager=skill_manager,
        tool_registry=tool_registry,
        log_file=str(log_file),
        uploads_dir=str(uploads_dir)
    )
    
    return agent, mcp_client
```

**改动点**：
1. `create_mcp_tools(...)` 返回值解包：`mcp_tools` → `mcp_tools, mcp_client`
2. 返回值：`return agent` → `return agent, mcp_client`
3. 返回类型标注：`-> Agent` → `-> tuple`（或更精确的 `-> Tuple[Agent, MCPClient]`）

##### 3.4.4 `_get_or_create_agent` — 保存 mcp_client 到缓存条目

**变更前**（`copilot_adapter.py:132-166`）：

```python
def _get_or_create_agent(self, session_id: str) -> Agent:
    with self._cache_lock:
        if session_id in self._agent_cache:
            entry = self._agent_cache[session_id]
            entry.touch()
            self._stats["cache_hits"] += 1
            return entry.agent
        
        self._stats["cache_misses"] += 1
    
    # 创建新的 Agent 实例（在锁外执行，避免阻塞）
    agent = self._create_agent(session_id)
    
    with self._cache_lock:
        # 双重检查
        if session_id not in self._agent_cache:
            self._agent_cache[session_id] = AgentCacheEntry(
                agent=agent,
                session_id=session_id
            )
            self._stats["active_sessions"] = len(self._agent_cache)
        else:
            agent = self._agent_cache[session_id].agent
    
    return agent
```

**变更后**：

```python
def _get_or_create_agent(self, session_id: str) -> Agent:
    with self._cache_lock:
        if session_id in self._agent_cache:
            entry = self._agent_cache[session_id]
            entry.touch()
            self._stats["cache_hits"] += 1
            return entry.agent
        
        self._stats["cache_misses"] += 1
    
    # 创建新的 Agent 实例（在锁外执行，避免阻塞）
    agent, mcp_client = self._create_agent(session_id)
    
    with self._cache_lock:
        # 双重检查
        if session_id not in self._agent_cache:
            self._agent_cache[session_id] = AgentCacheEntry(
                agent=agent,
                session_id=session_id,
                mcp_client=mcp_client,  # Phase 3: 保存 MCPClient 引用
            )
            self._stats["active_sessions"] = len(self._agent_cache)
        else:
            # 另一个线程已创建，清理本次多余的 mcp_client
            mcp_client.cleanup()
            agent = self._agent_cache[session_id].agent
    
    return agent
```

**改动点**：
1. `self._create_agent(session_id)` 返回值解包为 `agent, mcp_client`
2. `AgentCacheEntry(...)` 新增 `mcp_client=mcp_client`
3. 双重检查的 else 分支：**必须清理多余的 mcp_client**（两个线程同时创建同一 session，
   后到的那个 mcp_client 已经启动了 Docker 容器，不清理就泄漏了）

##### 3.4.5 `_cleanup_agent` — 过期清理回调（新增）

```python
def _cleanup_agent(self, session_id: str, entry: AgentCacheEntry):
    """
    Agent 过期时清理资源（由 CleanupTTLCache.__delitem__ 触发）。
    
    ⚠️ 此方法在 _cache_lock 内执行，绝对不能再获取 _cache_lock，否则死锁！
    """
    print(f"[CopilotBackend] Cleaning up session: {session_id}")
    
    # 1. 清理 MCP 客户端（停止 Docker 容器）— 必须先停容器再删文件
    if entry.mcp_client:
        try:
            entry.mcp_client.cleanup()
            print(f"[CopilotBackend] MCP container stopped for {session_id}")
        except Exception as e:
            print(f"[CopilotBackend] MCP cleanup error for {session_id}: {e}")
    
    # 2. 清理临时文件（容器已停止，不会有文件锁冲突）
    self._cleanup_temp_files(session_id)


def _cleanup_temp_files(self, session_id: str):
    """清理会话的临时脚本文件（审计留痕目录）"""
    import shutil
    temp_dir = Config.SESSIONS_ROOT / session_id / "temp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[CopilotBackend] Cleaned temp files for {session_id}")
```

**清理顺序很重要**：先停容器 → 再删文件。原因：
- Docker 容器挂载了 `/workspace`（映射到宿主机 `sessions/{session_id}/`）
- 如果先删文件再停容器，在 Windows 上可能因文件被容器进程占用而删除失败
- 容器停止后挂载解除，文件操作安全

##### 3.4.6 `cleanup_session` — 手动清理方法（已有，无需改动）

当前代码（`copilot_adapter.py:379-394`）：

```python
def cleanup_session(self, session_id: str) -> bool:
    with self._cache_lock:
        if session_id in self._agent_cache:
            del self._agent_cache[session_id]
            self._stats["active_sessions"] = len(self._agent_cache)
            return True
    return False
```

**无需改动**。`del self._agent_cache[session_id]` 会触发 `CleanupTTLCache.__delitem__`，
自动调用 `_cleanup_agent` 回调。但注意此处 `del` 在 `_cache_lock` 内执行，
所以 `_cleanup_agent` 也在锁内——与 3.4.5 的"不能再获取锁"约束一致，无问题。

#### 3.5 main.py 适配

**变更前**（`main.py:92-118`）：

```python
    # MCP 工具（Bash, Read, Write, List）
    mcp_tools = create_mcp_tools(
        session_id=derived_session_id,
        uploads_dir=str(session_uploads),
    )
    for tool in mcp_tools:
        tool_registry.register(tool)
        console.print(f"  [green]✓[/green] {tool.name:20s} - MCP 工具（容器内执行）")
    
    # ... 中间代码不变（UI 工具注册 L101-107，Agent 创建 L110-115）...
    
    # 保存 MCP 客户端引用以便清理（从工具实例中获取）
    agent._mcp_client = mcp_tools[0].client if mcp_tools else None
```

**变更后**：

```python
    # MCP 工具（Bash, Read, Write, List）
    mcp_tools, mcp_client = create_mcp_tools(
        session_id=derived_session_id,
        uploads_dir=str(session_uploads),
    )
    for tool in mcp_tools:
        tool_registry.register(tool)
        console.print(f"  [green]✓[/green] {tool.name:20s} - MCP 工具（容器内执行）")
    
    # ... 中间代码不变（UI 工具注册 L101-107，Agent 创建 L110-115）...
    
    # 保存 MCP 客户端引用以便清理（Phase 3: 使用工厂函数显式返回的引用）
    agent._mcp_client = mcp_client
```

**改动点**：
1. `create_mcp_tools(...)` 返回值解包：`mcp_tools` → `mcp_tools, mcp_client`
2. `agent._mcp_client = mcp_tools[0].client if mcp_tools else None` → `agent._mcp_client = mcp_client`

`main.py` 的 cleanup 逻辑（L240-258）**不需要改动**，因为它已经通过 `agent._mcp_client.cleanup()` 清理。

#### 3.6 实施注意事项

##### 3.6.1 [高] _cleanup_agent 中不能获取 _cache_lock

已在 3.4.5 说明。调用链总结：

```
_get_or_create_agent()                  # 场景1: 新增条目触发满容量驱逐
  └─ with self._cache_lock:
       └─ self._agent_cache[session_id] = entry   # __setitem__ 可能驱逐旧条目
            └─ __delitem__(old_key)
                 └─ _cleanup_agent(old_key, old_entry)   # ← 此时锁已被持有！

_start_cleanup_timer._periodic_expire()  # 场景2: 定时器触发过期驱逐
  └─ with self._cache_lock:
       └─ self._agent_cache.expire()
            └─ __delitem__(expired_key)
                 └─ _cleanup_agent(expired_key, entry)   # ← 此时锁已被持有！

cleanup_session()                        # 场景3: 手动清理
  └─ with self._cache_lock:
       └─ del self._agent_cache[session_id]
            └─ __delitem__(session_id)
                 └─ _cleanup_agent(session_id, entry)    # ← 此时锁已被持有！
```

三个场景中 `_cleanup_agent` 都在锁内执行。回调中**只能做**：
- `mcp_client.cleanup()`（I/O 操作，不涉及缓存锁）
- `shutil.rmtree()`（文件系统操作，不涉及缓存锁）
- `print()`（日志输出）

##### 3.6.2 [高] 双重创建时清理多余 mcp_client

见 3.4.4 的 else 分支。两个请求同时到达同一个新 session_id：
1. 线程 A 和线程 B 都通过缓存 miss
2. 线程 A 先创建完毕，写入缓存
3. 线程 B 也创建完毕，但发现缓存中已有 → 必须清理自己创建的 mcp_client

如果不清理，线程 B 创建的 Docker 容器会一直运行。

##### 3.6.3 [中] MCPClient.cleanup() 幂等性确认

当前实现（`mcp_tools.py:275-288`）在 `if self._process:` 保护下是幂等的。
可能被调用多次的场景：
1. `_cleanup_agent` 回调调用一次
2. GC 回收 MCPClient 时 `__del__` 再调一次

当前代码可以处理（`self._process` 已被置为 `None`），无需修改。

##### 3.6.4 [中] Windows 文件锁

Windows 上删除文件时，如果文件被其他进程打开会报 `PermissionError`。
`shutil.rmtree(temp_dir, ignore_errors=True)` 的 `ignore_errors=True` 已经处理了此情况，
最坏结果是临时文件残留，不影响功能。

##### 3.6.5 [低] debug 接口中 mcp_client 状态

`get_debug_info()` 可选增强：在会话列表中显示容器状态（是否已启动）。
Phase 3 暂不处理，后续按需添加。

#### 3.7 测试更新 (test_mcp_tool_classes.py)

##### 3.7.1 工厂函数测试更新

现有 4 个测试用例需要适配新返回值（`(tools, mcp_client)` 元组）：

**`test_returns_four_tools`**：

```python
# 变更前
tools = create_mcp_tools(session_id="test-session")
assert len(tools) == 4

# 变更后
tools, mcp_client = create_mcp_tools(session_id="test-session")
assert len(tools) == 4
assert mcp_client is not None
```

**`test_all_tools_are_base_tool`**：

```python
# 变更前
tools = create_mcp_tools(session_id="test-session")

# 变更后
tools, _ = create_mcp_tools(session_id="test-session")
```

**`test_no_python_tool`**：

```python
# 变更前
tools = create_mcp_tools(session_id="test-session")

# 变更后
tools, _ = create_mcp_tools(session_id="test-session")
```

**`test_no_output_dir_param`**：不涉及返回值，**不需要改**。

##### 3.7.2 新增测试：返回 MCPClient 实例

```python
@patch('agent_system.tools.mcp_tools.MCPClient')
@patch('agent_system.tools.mcp_tools.Config')
def test_returns_mcp_client(self, mock_config, mock_mcp_cls):
    """工厂函数返回 MCPClient 实例"""
    mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
    mock_config.SKILLS_DIR = Path("/tmp/test_skills")

    tools, mcp_client = create_mcp_tools(session_id="test-session")

    # mcp_client 应该是 MCPClient 的 mock 实例
    assert mcp_client is mock_mcp_cls.return_value


@patch('agent_system.tools.mcp_tools.MCPClient')
@patch('agent_system.tools.mcp_tools.Config')
def test_tools_share_same_mcp_client(self, mock_config, mock_mcp_cls):
    """所有工具共享同一个 MCPClient 实例"""
    mock_config.SESSIONS_ROOT = Path("/tmp/test_sessions")
    mock_config.SKILLS_DIR = Path("/tmp/test_skills")

    tools, mcp_client = create_mcp_tools(session_id="test-session")

    for tool in tools:
        assert tool.client is mcp_client
```

##### 3.7.3 新增测试：CleanupTTLCache（建议新建测试文件或在 test_mcp_tool_classes.py 末尾追加）

```python
class TestCleanupTTLCache:
    """CleanupTTLCache 自定义缓存测试"""

    def test_on_expire_called_on_manual_delete(self):
        """手动删除时触发 on_expire 回调"""
        expired = {}
        def on_expire(key, value):
            expired[key] = value

        cache = CleanupTTLCache(maxsize=10, ttl=300, on_expire=on_expire)
        cache["a"] = "value_a"
        del cache["a"]
        assert expired == {"a": "value_a"}

    def test_on_expire_called_on_ttl_expiry(self):
        """TTL 过期时触发 on_expire 回调"""
        import time
        expired = {}
        def on_expire(key, value):
            expired[key] = value

        cache = CleanupTTLCache(maxsize=10, ttl=0.1, on_expire=on_expire)  # 100ms TTL
        cache["a"] = "value_a"
        time.sleep(0.2)  # 等待过期
        cache.expire()   # 触发驱逐
        assert "a" in expired

    def test_on_expire_exception_does_not_block_delete(self):
        """回调异常不阻塞删除操作"""
        def on_expire(key, value):
            raise RuntimeError("cleanup failed")

        cache = CleanupTTLCache(maxsize=10, ttl=300, on_expire=on_expire)
        cache["a"] = "value_a"
        del cache["a"]  # 不应抛异常
        assert "a" not in cache

    def test_no_callback(self):
        """不传 on_expire 时行为与普通 TTLCache 一致"""
        cache = CleanupTTLCache(maxsize=10, ttl=300)
        cache["a"] = "value_a"
        del cache["a"]
        assert "a" not in cache

    def test_maxsize_eviction_triggers_callback(self):
        """容量满时驱逐最旧条目也触发回调"""
        expired = {}
        def on_expire(key, value):
            expired[key] = value

        cache = CleanupTTLCache(maxsize=2, ttl=300, on_expire=on_expire)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3  # 应驱逐 "a"
        assert "a" in expired
```

---

### Phase 4: Skill 文档与脚本更新 ✅ 已完成

**目标**：移除 `run_python_code` 相关内容，建立"Tier 1 CLI 直调 / Tier 2 组合扩展"分层执行策略，同步清理脚本中的废弃代码
**状态**：已完成（2026-02-12），32 个新增单元测试全部通过

#### 4.1 fin-advisor-math

##### 4.1.1 设计理念

旧版 SKILL.md 将执行策略分为"优先 CLI"和"备选 run_python_code"两条路径。实践中 Agent 几乎总是走 run_python_code 从零写代码，完全无视 skill 中已有的函数库。

新策略不是简单的"禁止 run_python_code"，而是建立 **"站在巨人肩膀上"** 的工作模式：

| 场景 | 旧行为（问题） | 新行为（期望） |
|------|---------------|---------------|
| CLI 能覆盖的标准计算 | Agent 偶尔用 CLI，但更喜欢自己写 | Tier 1：一行 Bash 搞定 |
| CLI 覆盖不了的复杂需求 | Agent 从零写代码，无视已有函数 | Tier 2：Read 已有函数 → Import 复用 → Write 组合脚本 → Bash 执行 |

##### 4.1.2 SKILL.md 改动清单

**移除的段落**：
- L14-28："⚡ 优先：CLI 直接执行" + "🔧 备选：run_python_code"（替换为 Tier 分层策略）
- L84-113：整个"🔧 复杂场景：使用 run_python_code" section（替换为 Tier 2 工作流）

**替换后的执行策略**：

```markdown
## 🚦 执行策略 (EXECUTION STRATEGY)

本技能的核心函数库位于 `scripts/finance_formulas.py`，支持两种使用方式。
**判断规则**：CLI 内置 `--type` 能覆盖 → Tier 1；否则 → Tier 2。

### Tier 1：CLI 直接调用（标准场景）

内置计算类型能覆盖的场景，一行 Bash 完成：

Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type <TYPE> <ARGS>")

脚本输出 JSON 结果，无需写任何代码。
详见下方「CLI 命令速查表」。

### Tier 2：组合扩展（复杂场景）

当 CLI 内置 type 无法覆盖需求时（如多方案对比、组合多种计算、自定义逻辑），
按以下工作流操作：

1. **Read**：先读源码了解可用函数
   Read("skills/fin-advisor-math/scripts/finance_formulas.py")

2. **Write**：编写组合脚本，**import 已有函数**而非从零实现
   Write("temp/multi_rate_compare.py", code)

3. **Bash**：执行脚本
   Bash("python temp/multi_rate_compare.py")

**关键原则**：你写的是"编排代码"（循环、组合、格式化），计算的核心逻辑必须 import 已有函数完成。

**Tier 2 示例**（多收益率对比）：

import sys
sys.path.insert(0, '/workspace/skills/fin-advisor-math/scripts')
from finance_formulas import calc_years_to_target
import json

rates = [0.06, 0.08, 0.10, 0.12]
results = []
for r in rates:
    years = calc_years_to_target(pv=300000, target_fv=1000000, annual_rate=r)
    results.append({"rate": f"{r*100:.0f}%", "years": round(years, 1)})

print(json.dumps(results, ensure_ascii=False, indent=2))

### ❌ 反模式（禁止）

- ❌ CLI 能覆盖的场景却自己写代码（浪费 token，不如一行 CLI）
- ❌ 不看已有函数就从头实现计算逻辑（重复造轮子，且可能算错）
- ❌ 使用 python -c 内联代码（无法审计追溯）
- ❌ 重新实现已有函数已覆盖的计算功能
```

**新增段落——可用函数清单**（插入 CLI 速查表之后）：

```markdown
## 🔧 可用函数清单（Tier 2 import 复用）

脚本路径：`skills/fin-advisor-math/scripts/finance_formulas.py`

| 函数 | 用途 | CLI --type |
|------|------|-----------|
| `calc_aip_fv(pmt, annual_rate, periods, freq)` | 定投终值 | aip |
| `calc_lump_sum_fv(pv, annual_rate, periods, freq)` | 一次性投资终值 | lump |
| `calc_cagr(pv, fv, years)` | 年化收益率 | cagr |
| `calc_years_to_target(pv, target_fv, annual_rate)` | 年限反推 | years |
| `calc_pmt_for_target(target_fv, annual_rate, periods, freq)` | 目标反推投入 | pmt |
| `calc_max_drawdown(nav_list)` | 最大回撤 | mdd |
| `calc_sharpe_ratio(returns, risk_free_rate)` | 夏普比率 | sharpe |
| `calc_irr(cash_flows)` | 内部收益率 | irr |

> 参数细节和返回值格式：`Read("skills/fin-advisor-math/scripts/finance_formulas.py")`
```

**其他改动**：
- CLI 示例中的 `bash(...)` 统一为 `Bash(...)` PascalCase
- 移除 L122 `ANALYSIS_RESULT_START/END` 相关表述（与 csv skill 相关，本 skill 未使用但保险起见检查）

##### 4.1.3 finance_formulas.py 改动

**移除 `setup_matplotlib_chinese()` 函数**（L198-231）：

可视化由前端 ECharts 负责（计算/展示分离原则），此函数已无用。移除后不影响任何 CLI 功能和 import 使用。

##### 4.1.4 实施注意事项

**import 路径**：Tier 2 脚本需要 `sys.path.insert(0, '/workspace/skills/fin-advisor-math/scripts')` 来 import 函数。这是当前最简方案，不涉及 Docker 镜像改动。未来可考虑在容器 PYTHONPATH 中预配置 skills 路径，但不在 Phase 4 scope 内。

#### 4.2 csv-data-summarizer

##### 4.2.1 设计理念

与 fin-advisor-math 本质不同：投顾计算的输入参数确定、公式固定，CLI + 函数库能覆盖绝大多数场景；而 CSV 分析面对的数据结构在运行前完全未知——列名、数据类型、领域含义、分析维度都取决于具体文件。一个写死的 `analyze_csv_pro()` 函数无法预见所有列名组合和分析需求。

因此 **不适用 Tier 1/Tier 2 分层模式**。这个 skill 天然是 "Agent 自己写代码" 的场景，skill 的价值不在于提供可调用的 CLI 或函数库，而在于：

| 价值层 | 内容 | 作用机制 |
|--------|------|----------|
| **代码模板** | `analyze.py` 作为参考实现 | Agent Read 后写出的代码风格趋同，降低报错风险、减少调试轮次（few-shot in code） |
| **领域知识** | 加权比率规则、周期完整性、CAGR/YoY、P&L 层级校验 | SKILL.md 注入到对话上下文，指导 Agent 遵循正确的分析方法 |
| **输出规范** | 结构化 JSON 格式、禁止 matplotlib | 确保 Orchestrator 能消费输出并调用 UI 工具 |
| **工作流指导** | Read CSV → 理解结构 → Write 分析脚本 → Bash 执行 | 引导 Agent 按正确顺序工作 |

**关键洞察**：`analyze.py` 的价值不是作为 CLI 工具被调用，而是作为 **代码范例** 被 Agent 阅读学习。实践中 Agent 读完 `analyze.py` 后写出的代码高度趋同，这种趋同是好事——它意味着 Agent 自然学会了 NpEncoder 模式、金融列检测逻辑、加权比率写法、pandas 惯用法等，无需在 SKILL.md 中用自然语言逐条描述。

##### 4.2.2 SKILL.md 改动清单

**整体结构调整**：从"调用 analyze.py CLI"转变为"Read 参考代码 → 理解数据 → 写分析脚本 → 执行"。

**移除/替换的内容**：
- "Example Python output pattern"（L93-119）：这段 inline Python 示例暗示 `run_python_code` 用法，替换为明确的 Write + Bash 工作流
- 隐含的 `run_python_code` 调用模式

**替换后的执行策略**：

```markdown
## 🚦 执行策略 (EXECUTION STRATEGY)

### 工作流

1. **Read CSV 概览**：读取前几行了解列名、数据类型、行数
   Read("uploads/data.csv", limit=20)

2. **Read 参考代码**：学习分析模式和最佳实践
   Read("skills/csv-data-summarizer/analyze.py")

3. **Write 分析脚本**：基于参考代码的模式，编写针对当前数据的分析脚本
   Write("temp/analysis_001.py", code)

4. **Bash 执行**：运行脚本获取结构化结果
   Bash("python temp/analysis_001.py")

5. **UI 展示**：基于结果调用 render_chart / render_table / show_notification

### 参考代码说明

`analyze.py` 是本 skill 的参考实现，**不作为 CLI 直接调用**，而是供你 Read 后学习以下模式：

- **NpEncoder**：处理 numpy 类型的 JSON 序列化
- **金融列检测**：通过关键词匹配识别 Revenue/Profit/Margin 等列
- **加权比率计算**：`total_profit / total_revenue` 而非 `df['margin'].mean()`
- **pandas 惯用法**：groupby、agg、sort_values 等数据处理模式

编写分析脚本时，优先复用参考代码中的模式，而非从零发明。

### ❌ 反模式（禁止）

- ❌ 不看参考代码就从零写分析逻辑（容易遗漏加权比率等领域规则）
- ❌ 使用 matplotlib/seaborn 生成图片（可视化由前端 ECharts 负责）
- ❌ 使用 python -c 内联代码（无法审计追溯）
- ❌ 输出 ANALYSIS_RESULT_START/END 标记（已废弃）
- ❌ 输出 charts 数组（已废弃，应输出 data 对象）
```

**保留不变的内容**：
- "CRITICAL BEHAVIOR REQUIREMENT"（L15-58）：立即分析、不要问用户想干什么——这个行为指导仍然有效
- "Domain Expertise: Financial Analysis Principles"（L60-71）：领域知识核心，保留
- "JSON Output Structure"（L124-165）：输出格式规范，保留
- "Visualization Guidelines (FOR ORCHESTRATOR)"（L167-181）：Orchestrator 指导，保留

##### 4.2.3 analyze.py 改动清单

定位从"CLI 工具"变为"参考实现/代码模板"，需要清理废弃协议使其作为范例代码是正确的：

**改动 1：移除 `ANALYSIS_RESULT_START/END` 标记**（L109-111）

```python
# 变更前
print("ANALYSIS_RESULT_START")
print(json.dumps(result, cls=NpEncoder, ensure_ascii=False, indent=2))
print("ANALYSIS_RESULT_END")

# 变更后
print(json.dumps(result, cls=NpEncoder, ensure_ascii=False, indent=2))
```

**改动 2：`charts` 数组改为 `data` 对象**（L19 及所有 `result["charts"].append(...)` 调用）

```python
# 变更前
result = {
    "summary": {"rows": int(df.shape[0]), "cols": int(df.shape[1])},
    "insights": [],
    "charts": []
}
# ... 后续多处 result["charts"].append({...})

# 变更后
result = {
    "summary": {"rows": int(df.shape[0]), "cols": int(df.shape[1])},
    "insights": [],
    "data": {}
}
# 图表配置改为结构化数据（供 Orchestrator 决策可视化方式）
# 例如：result["data"]["revenue_trend"] = {"labels": [...], "values": [...]}
#       result["data"]["margin_by_category"] = {"Product A": 0.42, ...}
```

具体来说，需要改写以下位置：
- L67-73：Revenue Trend → `result["data"]["revenue_trend"] = {"labels": labels, "values": values}`
- L81-87：Margin by Category → `result["data"]["margin_by_category"] = {"categories": [...], "margins": [...]}`
- L92-99：Revenue Composition → `result["data"]["revenue_composition"] = {name: value, ...}`

**改动 3：保留 CLI 入口但补充说明注释**（L113-116）

```python
# 变更前
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        analyze_csv_pro(sys.argv[1])

# 变更后
if __name__ == "__main__":
    # 本脚本主要作为参考实现供 Agent 学习分析模式，
    # 也可直接执行进行快速概览：python analyze.py <csv_path>
    import sys
    if len(sys.argv) > 1:
        analyze_csv_pro(sys.argv[1])
    else:
        print(json.dumps({"error": "Usage: python analyze.py <csv_file_path>"}))
```

##### 4.2.4 实施注意事项

**`charts` → `data` 重构需要仔细处理**：当前 `analyze.py` 中有 3 处 `result["charts"].append(...)`，每处都包含完整的 ECharts 配置（type/title/xAxis/yAxis/series）。重构时需要将这些配置拆解为纯数据（不含可视化 type/title 等），因为"用什么图表展示"是 Orchestrator 的决策，不是 skill 的职责。

**文件头注释更新**：`analyze.py` 的文件头应标注"参考实现"定位，避免后续开发者误以为这是一个正式的 CLI 工具。

---

## 4. 未来扩展点

### 4.1 银行接入后可能添加的工具

| 工具 | 触发条件 | 说明 |
|-----|---------|------|
| `glob` / `grep` | 文件数量多，需要搜索 | 按文件名/内容搜索 |
| `http_request` | 需要调用外部 API | 通用 HTTP 请求 |
| `query_sql` | 银行提供数据库访问 | SQL 查询 |
| `vector_search` | 非结构化文档多，需要 RAG | 语义搜索 |

### 4.2 PTC 预留

在工具定义中预留 `allowed_callers` 字段，为未来 Programmatic Tool Calling 做准备：

```python
TOOL_METADATA = {
    "Read": {"allowed_callers": ["agent", "code_execution"]},
    "Write": {"allowed_callers": ["agent", "code_execution"]},
    "List": {"allowed_callers": ["agent", "code_execution"]},
    "Bash": {"allowed_callers": ["agent"]},
    "run_python": {"allowed_callers": ["code_execution"]},  # 保留，仅 PTC 可调用
}
```

---

## 5. 测试计划

### 5.1 单元测试

- [x] `Read` MCP 工具：正常读取、路径越界、文件不存在、编码处理（13 个用例）
- [x] `Write` MCP 工具：正常写入、只读区域拒绝、追加模式、路径越界（9 个用例）
- [x] `List` MCP 工具：目录列表、递归、glob 匹配（10 个用例）
- [x] `Bash` 输出截断：头尾保留策略、超时、退出码（5 个用例）
- [x] 安全辅助函数：`_validate_path`、`_is_readonly`、`_count_lines`、`_truncate_output`（20 个用例）
- [x] 冻结工具验证：函数体保留、可直接调用（4 个用例）
- [x] 端到端场景：write→read 审计留痕、list→read、CSV 分页工作流（4 个用例）
- [x] `BashTool`（Python 侧）：白名单 python/python3、拒绝 -c/-m、拒绝其他命令、shlex 解析、危险字符检查、输出截断（22 个用例）
- [x] `MCPToolBase._format_result()`：成功/失败/中文保留（4 个用例）
- [x] `ReadTool`/`WriteTool`/`ListTool`（Python 侧）：参数 schema、execute 调用链、MCP 异常处理（18 个用例）
- [x] `create_mcp_tools` 工厂函数：返回 4 工具、无 PythonTool、无 output_dir 参数（4 个用例）
- [x] 工具 description 路由-接口验证：Read/Write/List/Bash 各 description 内容（4 个用例）
- [ ] `create_mcp_tools` 返回元组：返回 `(tools, mcp_client)`、MCPClient 实例校验、所有工具共享同一 client（3 个用例，更新现有 3 个用例）
- [ ] `CleanupTTLCache`：手动删除触发回调、TTL 过期触发回调、回调异常不阻塞删除、无回调兼容、满容量驱逐触发回调（5 个用例）

> 测试文件：
> - `tests/test_mcp_server_tools.py`（Phase 1 Docker 端），共 65 个用例，全部通过
> - `tests/test_mcp_tool_classes.py`（Phase 2 Python 侧），共 54 个用例（含 Phase 3 新增 2 个），全部通过
> - `tests/test_cleanup_ttl_cache.py`（Phase 3 CleanupTTLCache），共 7 个用例，全部通过
> - **合计 126 个用例**

### 5.2 集成测试

- [ ] Skill CLI 流程：Skill 加载 → Bash 执行脚本 → 返回结果
- [ ] Write + Bash 流程：Write 写脚本 → Bash 执行 → 验证结果 → 文件可追溯
- [ ] Web 模式容器清理：会话过期 → `_cleanup_agent` 回调触发 → `mcp_client.cleanup()` 被调用 → 容器停止 → 临时文件清理
- [ ] Web 模式手动清理：`DELETE /copilotkit/sessions/{id}` → 容器正确清理
- [ ] 双重创建竞争：两个线程同时创建同一 session → 只保留一个容器，多余的被清理

### 5.3 回归测试

- [ ] fin-advisor-math 所有计算类型
- [ ] csv-data-summarizer 数据分析流程

---

## 6. 风险与缓解

| 风险                                   | 影响 | 缓解措施                                        |
| -------------------------------------- | ---- | ----------------------------------------------- |
| Skill CLI 脚本覆盖不全                 | 高   | Tier 1 CLI 覆盖标准场景；Tier 2 允许 import 已有函数组合扩展作为兜底 |
| LLM 无视已有函数从零写计算代码          | 中   | SKILL.md 分层策略引导；函数清单索引降低 Read 成本；反模式列表明确禁止 |
| 容器清理时机不当导致数据丢失           | 中   | 先写 output 再清理 temp                         |
| 审计日志存储空间                       | 低   | 定期清理历史 session                            |

---

## 7. 时间线

| Phase   | 内容                                             | 预估工作量 |
| ------- | ------------------------------------------------ | ---------- |
| Phase 1 | MCP 工具层重构 (server.py)                       | 2h ✅      |
| Phase 2 | 工具层适配 (mcp_tools.py + prompts.py)           | 3h ✅      |
| Phase 3 | Web 模式容器泄漏修复 + MCPClient 引用规范化       | 1.5h ✅    |
| Phase 4 | Skill 文档与脚本更新（SKILL.md + analyze.py + finance_formulas.py + skill_tool.py） | 2h ✅      |
| 测试    | 单元测试 + 集成测试                              | 2h         |

**总计**：约 10.5 小时（Phase 1-4 已完成约 8.5h，剩余集成测试约 2h）

---

## 8. 变更日志

| 日期       | 版本 | 变更内容                                                                                                                          |
| ---------- | ---- | --------------------------------------------------------------------------------------------------------------------------------- |
| 2026-01-29 | v0.1 | 初始规划                                                                                                                          |
| 2026-01-29 | v0.2 | 简化为"最小通用基座"；确认移除 run_python_code（审计留痕）；确认暂不添加 glob/grep；明确 bash 定位（Skill CLI + write+bash 留痕） |
| 2026-02-09 | v0.3 | Review 补充改进：read_file total_lines 性能优化（rb 模式）；行号格式统一为 `{line_no:6d}\|{line_content}`；路径校验补充 symlink 边界说明；write_file 增加 MAX_WRITE_SIZE 1MB 限制；Bash 输出截断改为头尾保留策略；REPL 工具区块注释增强；编码降级返回 actual_encoding 字段；list_files 返回 total_count 字段；Phase 2 ReadFileTool 参数同步为 offset+limit；新增 2.4 跨 Phase 接口一致性说明 |
| 2026-02-09 | v0.4 | **Phase 1 实施完成**。变更文件：`docker-sandbox/server.py`（重写），`tests/test_phase1_mcp_server_tools.py`（新增）。具体改动：新增 read_file/write_file/list_files 三个 MCP 原子工具；新增 `_validate_path`（is_relative_to）、`_is_readonly`、`_count_lines`（1MB 块计数）、`_truncate_output`（头80%+尾20%保留）四个安全辅助函数；exec_command 增加输出截断保护且 cwd 改用 WORKSPACE 常量；冻结 run_python/reset_context/get_context_info 三个 REPL 工具（注释 @mcp.tool 装饰器，保留函数体）；65 个单元测试覆盖全部工具和边界场景（路径遍历、只读拒绝、GBK 降级、分页、截断、大小限制等） |
| 2026-02-09 | v0.5 | **Phase 1 验收通过**。文档改动：1.1/1.2/1.3 节从旧规格直接替换为与实际代码一致的版本（消除前后矛盾）；新增 1.5 Tech Debt 节记录两个验收发现的问题（read_file readlines 大文件双重 I/O、write_file bytes_written 字段名语义不准确），含修复方案供 coding agent 参考 |
| 2026-02-09 | v0.6 | **Tech Debt #1 #2 修复**。read_file 改为单次 pass 逐行读取（消除 `_count_lines()` + `readlines()` 双重全量 I/O），内存只持有 limit 行；write_file 返回字段 `bytes_written` 改名为 `chars_written`（语义准确）；2.4 接口一致性表同步更新；65 个单元测试全部通过 |
| 2026-02-09 | v0.7 | **Phase 2 规划完善**。基于 CC 工具体系分析，重写 Phase 2 规划：（1）工具 description 移除冗余环境信息，对齐 CC 路由-接口解耦原则；（2）新增 2.4 `MCPToolBase` 基类和 `_format_result()` 公共方法；（3）BashTool 增加反向路由 description、`shlex.split()`、危险字符检查、输出二次截断；（4）新增 2.6 System Prompt 更新规划（路由-接口协同验证表）；（5）新增 2.7 `create_mcp_tools` 清理；（6）工具类补全 `__init__`、`execute` 签名 |
| 2026-02-09 | v0.8 | **LLM 工具命名对齐 CC**。所有 LLM 可见工具名统一为 PascalCase：`Read`/`Write`/`List`/`Bash`（与 CC 的 Read/Write/Bash/Glob/Grep/Edit/Skill 风格一致）。Python 类名同步更新：`ReadFileTool`→`ReadTool`、`WriteFileTool`→`WriteTool`、`ListFilesTool`→`ListTool` |
| 2026-02-09 | v0.9 | **全栈命名统一**。将 MCP 协议层工具名也统一为 PascalCase，消除双层命名映射。Docker 端通过 `@mcp.tool(name="Read")` 覆盖（Python 函数名保持 snake_case / PEP 8）。影响范围：（1）架构图移除双层标注；（2）工具清单表移除 MCP 列；（3）Phase 1 所有 `@mcp.tool()` 改为 `@mcp.tool(name="...")` 覆盖；（4）Phase 2 所有 `call_tool("read_file")` 改为 `call_tool("Read")` 等；（5）接口一致性表、PTC 预留、测试计划、Tech Debt 标题同步更新；（6）变更日志条目同步 |
| 2026-02-09 | v0.10 | **Phase 2 审计补充**。四项补充：（1）2.0 节新增测试文件命名策略——Phase 2 完成后 `test_phase1_*` 统一改名为 `test_mcp_server_tools.py`，Python 侧工具类测试建议新建 `test_mcp_tool_classes.py`；（2）2.4 节新增 `_format_result()` 设计决策说明——成功返回完整 JSON 而非纯文本的三点理由及后续优化方向；（3）2.7 节"注意"段落替换为完整调用点变更清单（`copilot_adapter.py` L195-198 代码 diff、`__init__.py` L11-33 导出清理 diff、`server/app.py` 确认说明）；（4）`__init__.py` 导出清理与 `copilot_adapter.py` 影响范围并入 2.7 |
| 2026-02-09 | v0.11 | **Phase 2 实施完成**。变更文件 7 个：（1）`docker-sandbox/server.py`——`@mcp.tool()` 补充 `name` 参数覆盖（Read/Write/List/Bash），文件头注释和常量区注释同步更新为 PascalCase；（2）`agent_system/tools/mcp_tools.py`——新增 `MCPToolBase` 基类（含 `_format_result()`）和 `ReadTool`/`WriteTool`/`ListTool` 三个工具类，`BashTool` 重写（白名单缩减为 python/python3、`shlex.split()`、反向路由 description、输出二次截断），移除 `PythonTool` 类，`create_mcp_tools()` 移除 `output_dir` 参数并返回 4 工具；（3）`agent_system/agent/prompts.py`——Tool usage policy 重写为正向路由 + Write+Bash 审计留痕模式，Doing tasks 追加 Read-first 指令；（4）`agent_system/tools/__init__.py`——导出清理，移除 PythonTool，新增 MCPToolBase/ReadTool/WriteTool/ListTool；（5）`server/copilot_adapter.py`——`create_mcp_tools()` 调用移除 `output_dir` 参数；（6）`tests/test_phase1_mcp_server_tools.py` → `tests/test_mcp_server_tools.py`（重命名 + Mock `tool(**kwargs)` 兼容）；（7）`tests/test_mcp_tool_classes.py`（新增 52 个用例）。合计 117 个单元测试全部通过 |
| 2026-02-09 | v0.12 | **Phase 3 规划完善**。采用方案 B（显式返回 MCPClient 引用）重写 Phase 3：（1）`create_mcp_tools()` 返回 `(List[BaseTool], MCPClient)` 元组，消除 `main.py` 中 `mcp_tools[0].client` 的 hack；（2）`AgentCacheEntry` 新增 `mcp_client` 字段；（3）新增 `CleanupTTLCache` 自定义缓存类（继承 TTLCache，`__delitem__` 触发回调），含死锁防护（`Cache.__getitem__` 绕过递归驱逐）和回调异常隔离；（4）`CopilotBackend.__init__` 切换为 CleanupTTLCache + 后台定时器线程（解决懒惰驱逐问题，`expire()` 需 cachetools 6.2.4 支持）；（5）`_get_or_create_agent` 双重检查分支增加多余 mcp_client 清理；（6）新增 `_cleanup_agent` 和 `_cleanup_temp_files` 方法，清理顺序为先停容器再删文件；（7）3.6 节 6 项实施注意事项（死锁、双重创建竞争、cleanup 幂等性、Windows 文件锁等）；（8）3.7 节测试规划含 3 个现有测试更新 + 2 个新增工厂函数测试 + 5 个 CleanupTTLCache 测试；（9）更新 5.1/5.2 测试计划条目 |
| 2026-02-12 | v0.13 | **Phase 3 实施完成**。变更文件 4 个：（1）`server/copilot_adapter.py`——新增 `CleanupTTLCache` 类（使用 `_value_store` 字典解决 TTL 过期时 `self.get()` 返回 `None` 的问题，重写 `expire()` 确保 TTL 过期也能触发回调），`AgentCacheEntry` 新增 `mcp_client` 字段，`CopilotBackend.__init__` 使用 `CleanupTTLCache` + 后台定时器，新增 `_start_cleanup_timer`/`_cleanup_agent`/`_cleanup_temp_files` 方法，`_create_agent` 返回 `(Agent, MCPClient)` 元组，`_get_or_create_agent` 保存 MCPClient 引用并处理竞态条件下的重复清理；（2）`agent_system/tools/mcp_tools.py`——`create_mcp_tools()` 返回值从 `List[BaseTool]` 改为 `Tuple[List[BaseTool], MCPClient]`；（3）`agent_system/main.py`——适配新返回值，移除从工具实例获取 client 的 hack；（4）`tests/test_cleanup_ttl_cache.py`（新增 7 个用例，覆盖手动删除、TTL 过期、容量驱逐、回调异常隔离等场景）；（5）`tests/test_mcp_tool_classes.py`——新增 2 个测试（`test_returns_mcp_client`、`test_tools_share_same_mcp_client`）。合计 126 个单元测试全部通过 |
| 2026-02-12 | v0.14 | **Phase 4 规划完成**。两个 skill 采用完全不同的执行策略：**fin-advisor-math** 采用 Tier 分层模式——Tier 1 CLI 直调覆盖标准计算，Tier 2 Read→Import→Write→Bash 覆盖复杂需求，新增函数清单索引表（8 个函数），反模式改为"禁止无视已有函数从零写代码"，`finance_formulas.py` 移除废弃的 `setup_matplotlib_chinese()`；**csv-data-summarizer** 采用"代码模板"模式——`analyze.py` 定位从 CLI 工具变为参考实现（Agent Read 后写出趋同代码，降低报错风险），SKILL.md 工作流改为 Read CSV→Read 参考代码→Write 分析脚本→Bash 执行，`analyze.py` 清理废弃协议（移除 `ANALYSIS_RESULT_START/END`、`charts` 改 `data`）；时间线 Phase 4 从 0.5h 上调至 2h |
| 2026-02-12 | v0.15 | **Phase 4 实施完成**。变更文件 6 个：（1）`skills/fin-advisor-math/scripts/finance_formulas.py`——移除 `setup_matplotlib_chinese()` 函数，新增 `--cashflows` 参数和 `irr` CLI 分支，epilog 添加 IRR 示例；（2）`skills/fin-advisor-math/SKILL.md`——重写为 Tier 1/Tier 2 执行策略，`bash()` → `Bash()` PascalCase，新增可用函数清单表（8 个函数），新增 IRR 到 CLI 速查表，移除 `run_python_code` 引用；（3）`skills/csv-data-summarizer/SKILL.md`——新增 Read→Write→Bash 执行策略，说明 `analyze.py` 作为参考实现定位，列出反模式，标注 `ANALYSIS_RESULT_START/END` 和 `charts` 数组已废弃；（4）`skills/csv-data-summarizer/analyze.py`——文件头添加参考实现说明，`charts` 数组改为 `data` 对象（3 处 append 改为 key 赋值），移除 `ANALYSIS_RESULT_START/END` 标记，CLI 入口添加说明注释；（5）`agent_system/tools/skill_tool.py`——CRITICAL RULES 清理 `run_python_code` 引用，改为新工具名；（6）`tests/test_phase4_skill_purification.py`——重写测试类（7 个类 32 个用例），覆盖 prompts.py 审计留痕模式、fin-advisor-math Tier 策略、csv-data-summarizer 工作流、analyze.py 重构、finance_formulas.py 更新、skill_tool.py 清理、UI 工具集成。合计 158 个单元测试全部通过（Phase 1-3: 126 + Phase 4: 32） |