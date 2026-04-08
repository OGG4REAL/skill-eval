# WebSearch / WebExtract 规划与技术设计

## 1. 文档定位

本文用于定义项目中“联网搜索能力”的第一版规划与技术接口。

目标不是立即实现完整的网页研究系统，而是先把以下事情定清楚：

- 为什么当前阶段选择“内建工具”而不是 MCP server
- `WebSearch` 与 `WebExtract` 的职责边界
- 第一版只做 `WebSearch` 时，接口应如何设计
- 为什么工具 schema 应保持 provider-neutral，而不是直接暴露 Tavily 原生字段
- 后续如果接入 `WebExtract`，应如何自然演进而不破坏已有接口

本文面向两个对象：

1. 实现者
   - 需要知道后端该如何落地
2. 评估与调优者
   - 需要知道工具契约、轨迹信号和后续 benchmark 如何围绕该能力扩展

## 2. 结论先行

### 2.1 本阶段结论

当前阶段建议：

- 先实现一个内建工具：`WebSearch`
- 暂不实现 `WebExtract`，但提前定义好 schema 与演进路径
- 底层 provider 先使用 `Tavily`
- 工具对模型暴露的名称与参数保持 provider-neutral
- 在系统提示词中明确要求：引用搜索结果回答问题时，最终答复必须附带 `Sources`

### 2.2 为什么不先做 MCP server

当前项目里，联网搜索更适合作为 Agent runtime 的一等工具，而不是独立的 MCP 外挂能力。

原因：

- 当前项目已有稳定的内建工具注册链路
- 现有 MCP 体系主要服务于本地 Docker 沙箱内的原子文件/执行能力
- Web Search 是“外部知识获取能力”，语义上更接近平台原生工具
- 先做内建工具，接入路径最短，调试、记录 trajectory、做评测都更直接

只有当后续出现以下需求时，才值得升级为 MCP server：

- 多个宿主共享同一联网能力
- 需要多 provider 统一编排
- 需要独立部署、鉴权、限流与观测
- 需要将搜索能力作为平台级外设提供给多个 Agent

## 3. 设计目标

本轮设计希望同时满足五个目标：

1. Agent 能查询知识截止之后的最新信息
2. 工具接口足够简单，模型容易学会使用
3. 返回结果可追溯，便于最终回答附来源
4. 不把工具契约绑死在某个搜索供应商上
5. 后续增加 `WebExtract` 时，不需要推翻第一版设计

## 4. 能力边界

### 4.1 `WebSearch` 的职责

`WebSearch` 负责：

- 根据查询检索网络来源
- 返回高相关结果及其摘要片段
- 支持域名过滤与时间范围过滤
- 为最终回答提供可引用的来源 URL

`WebSearch` 不负责：

- 对单个网页做深度正文提取
- 对长文档做结构化精读
- 对整站做 crawl / map
- 执行多轮研究代理流程

### 4.2 `WebExtract` 的职责

`WebExtract` 负责：

- 对一个或多个已知 URL 提取正文
- 支持精读官方文档、公告页、博客文章、定价页等
- 为复杂问答提供更完整上下文与证据

`WebExtract` 不负责：

- 替代搜索召回
- 做大规模站点遍历
- 做研究代理式多步综合分析

### 4.3 两者关系

完整链路应理解为：

```text
WebSearch
  -> 找来源、做粗读、建立可信出处
  -> 如摘要已足够，则直接回答
  -> 如需要正文细节、参数核验、长文总结
  -> WebExtract
```

也就是说：

- `WebSearch` 是召回 + 粗读
- `WebExtract` 是精读 + 取证

## 5. 为什么第一版先只做 `WebSearch`

虽然从完整链路看，`search + extract` 才是最终形态，但当前阶段先做 `WebSearch` 仍然合理。

原因：

- 当前最明确的需求是“让 Agent 获得最新信息”
- 这类需求很多时候只需要高质量搜索结果与来源即可
- `WebSearch` 能先验证联网能力对当前产品是否真的有价值
- `WebExtract` 的触发策略、内容粒度、成本控制、评测方式仍未完全收敛

因此本阶段采用：

- `v1`: 实现 `WebSearch`
- `vNext`: 视真实使用场景，再接入 `WebExtract`

## 6. Provider-neutral 原则

### 6.1 总体原则

工具名称、参数和返回结构应体现“能力语义”，而不是“供应商 API 术语”。

换句话说：

- 工具名应是 `WebSearch`，而不是 `TavilySearch`
- 工具名应是 `WebExtract`，而不是 `TavilyExtract`
- 返回值应使用项目自己的抽象字段，而不是无差别透传 provider 原生字段

### 6.2 为什么不直接暴露 Tavily 原生字段

不建议直接把 Tavily 原生 schema 暴露给模型，主要因为：

1. 供应商耦合过强
   - 后续替换 provider 或增加 fallback 时，prompt、评测、工具使用行为都会受影响
2. 供应商术语不等于 Agent 语义
   - 某些字段对 API 使用者合理，但对 LLM 并不是最直观的表达
3. 评测与轨迹分析会更脆弱
   - 工具层若直接暴露供应商字段，长期统计与 benchmark 规则会被供应商细节污染
4. 部分原生参数不适合当前阶段暴露
   - 例如某些自动调参能力会让工具行为更黑箱，不利于调试和评测

### 6.3 抽象原则

建议遵循以下规则：

- 输入参数：保留稳定、通用、对模型有帮助的参数
- 输出字段：统一为项目自己的语义命名
- provider request id、usage 等字段可保留为可选调试信息

例如：

- 用 `allowed_domains`，而不是强依赖供应商命名
- 用 `blocked_domains`，而不是直接暴露 provider 的排除字段
- 用 `snippet` 表示搜索结果摘要
- 用 `content` 表示提取后的正文内容

## 7. `WebSearch` 工具定义

### 7.1 设计目标

`WebSearch` 的 schema 应尽量简洁，但保留后续真实使用一定会用到的过滤能力。

第一版重点支持：

- 查询
- 域名 include / exclude
- 主题类型
- 时间范围
- 结果数量
- 搜索深度

### 7.2 Function Schema

```json
{
  "name": "WebSearch",
  "description": "搜索网络上的最新信息并返回结构化结果。适合查找最新文档、公告、版本信息、新闻和知识截止之后的事实。使用搜索结果回答用户时，最终答复必须附带 Sources 部分并列出实际引用的来源链接。",
  "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "minLength": 2,
        "description": "搜索查询。应尽量具体，必要时包含产品名、版本号、年份或限定词。"
      },
      "allowed_domains": {
        "type": "array",
        "description": "仅允许这些域名进入结果，例如 [\"react.dev\", \"nextjs.org\"]。",
        "items": {
          "type": "string",
          "minLength": 1
        },
        "maxItems": 50
      },
      "blocked_domains": {
        "type": "array",
        "description": "排除这些域名，避免低质量或不可信来源。",
        "items": {
          "type": "string",
          "minLength": 1
        },
        "maxItems": 50
      },
      "topic": {
        "type": "string",
        "description": "搜索主题类型。默认 general。",
        "enum": ["general", "news", "finance"],
        "default": "general"
      },
      "time_range": {
        "type": "string",
        "description": "按时间范围过滤结果。仅在需要最新信息时使用。",
        "enum": ["day", "week", "month", "year"],
        "default": "month"
      },
      "max_results": {
        "type": "integer",
        "description": "返回结果数量上限。默认 5。",
        "minimum": 1,
        "maximum": 10,
        "default": 5
      },
      "search_depth": {
        "type": "string",
        "description": "搜索深度。basic 更省成本更快，advanced 更偏高质量召回。",
        "enum": ["basic", "advanced"],
        "default": "basic"
      }
    },
    "required": ["query"],
    "additionalProperties": false
  }
}
```

### 7.3 返回结构建议

建议 `WebSearch` 返回如下项目内部统一结构：

```json
{
  "query": "React 19 server actions documentation 2026",
  "provider": "tavily",
  "topic": "general",
  "results": [
    {
      "title": "React Docs",
      "url": "https://react.dev/...",
      "snippet": "Server Actions let you...",
      "domain": "react.dev",
      "score": 0.97,
      "published_date": null
    }
  ],
  "sources": [
    "https://react.dev/..."
  ],
  "request_id": "optional-provider-request-id"
}
```

### 7.4 返回字段说明

- `query`
  - 实际执行的查询，便于调试与 run 追踪
- `provider`
  - 当前实现供应商，便于观测但不影响工具语义
- `results`
  - 搜索结果主数组
- `results[].snippet`
  - 面向模型的摘要片段，不直接暴露供应商原始命名
- `results[].domain`
  - 建议后端从 URL 解析补齐，便于评测与过滤分析
- `sources`
  - 汇总出的可引用 URL 列表，供最终答复的 `Sources` 直接使用
- `request_id`
  - 可选调试字段，用于排查 provider 请求

## 8. `WebExtract` 预留定义

### 8.1 为什么现在先定义不实现

虽然当前阶段暂不实现 `WebExtract`，但提前定义 schema 有三个好处：

- 文档中能明确完整演进方向
- 后续实现时不必重新讨论接口命名
- 现在就能在系统提示词和评测设计中预留精读能力的边界

### 8.2 Function Schema

```json
{
  "name": "WebExtract",
  "description": "从一个或多个已知 URL 提取网页正文内容。适合在已找到可靠来源后，对页面进行精读、长文总结、参数核对和证据补强。",
  "parameters": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
      "urls": {
        "type": "array",
        "description": "需要提取内容的 URL 列表。建议优先传官方文档、公告页或已通过 WebSearch 命中的高质量来源。",
        "items": {
          "type": "string",
          "format": "uri",
          "minLength": 1
        },
        "minItems": 1,
        "maxItems": 10
      },
      "query": {
        "type": "string",
        "description": "可选。用于告诉提取器当前最关心什么内容，以便对正文片段进行相关性排序。"
      },
      "extract_depth": {
        "type": "string",
        "description": "提取深度。basic 更快更便宜，advanced 更适合表格、复杂正文和嵌入内容。",
        "enum": ["basic", "advanced"],
        "default": "basic"
      },
      "format": {
        "type": "string",
        "description": "返回内容格式。默认 markdown。",
        "enum": ["markdown", "text"],
        "default": "markdown"
      },
      "include_images": {
        "type": "boolean",
        "description": "是否返回页面图片链接。",
        "default": false
      },
      "include_favicon": {
        "type": "boolean",
        "description": "是否返回页面 favicon。",
        "default": false
      },
      "chunks_per_source": {
        "type": "integer",
        "description": "当提供 query 时，每个来源最多返回多少个高相关内容片段。",
        "minimum": 1,
        "maximum": 5,
        "default": 3
      },
      "timeout_seconds": {
        "type": "number",
        "description": "单次提取超时秒数。",
        "minimum": 1,
        "maximum": 60,
        "default": 20
      }
    },
    "required": ["urls"],
    "additionalProperties": false
  }
}
```

### 8.3 返回结构建议

```json
{
  "provider": "tavily",
  "results": [
    {
      "url": "https://react.dev/...",
      "content": "# Server Actions\n...",
      "content_format": "markdown",
      "favicon": "https://react.dev/favicon.ico",
      "images": []
    }
  ],
  "failed_results": [
    {
      "url": "https://example.com/...",
      "error": "Timeout"
    }
  ],
  "request_id": "optional-provider-request-id"
}
```

## 9. 与 Tavily 的映射关系

### 9.1 为什么选择 Tavily

当前阶段优先选择 Tavily 的原因：

- 对 Agent 场景友好，返回结果已经过相关性优化
- `search` 能返回摘要级结果，不只是 URL 列表
- 后续若需要精读，可自然接入 `extract`
- 再往后若需要更复杂站点级能力，也有 `crawl` / `map` 可接

### 9.2 `WebSearch` 到 Tavily Search 的映射

推荐映射关系：

- `query` -> Tavily `query`
- `allowed_domains` -> Tavily `include_domains`
- `blocked_domains` -> Tavily `exclude_domains`
- `topic` -> Tavily `topic`
- `time_range` -> Tavily `time_range`
- `max_results` -> Tavily `max_results`
- `search_depth` -> Tavily `search_depth`

返回值建议做一层归一化：

- Tavily `results[].content` -> `results[].snippet`
- Tavily `results[].url` 保留
- Tavily `results[].title` 保留
- Tavily `results[].score` 保留
- Tavily `answer` 暂不作为主字段暴露给上层
- Tavily `raw_content` 不纳入 `WebSearch` 第一版主返回结构

### 9.3 为什么不把 Tavily `answer` 作为主返回

不建议把 Tavily 的 `answer` 直接当作工具主结果，原因：

- 它会把“搜索能力”和“回答生成能力”混在一起
- 当前项目已有自己的主 Agent 负责最终回答
- 若直接依赖 provider answer，会削弱对主 Agent 推理质量的观测
- 后续做 benchmark 时，也更难区分“检索质量”和“回答质量”

因此更建议：

- `WebSearch` 返回结果与来源
- 最终回答仍由主 Agent 生成

### 9.4 `WebExtract` 到 Tavily Extract 的映射

推荐映射关系：

- `urls` -> Tavily `urls`
- `query` -> Tavily `query`
- `extract_depth` -> Tavily `extract_depth`
- `format` -> Tavily `format`
- `include_images` -> Tavily `include_images`
- `include_favicon` -> Tavily `include_favicon`
- `chunks_per_source` -> Tavily `chunks_per_source`

返回归一化建议：

- Tavily `results[].raw_content` -> `results[].content`
- 额外补 `content_format`

## 10. 使用策略建议

### 10.1 当前阶段的系统提示词原则

建议在系统提示词中明确：

1. 当问题依赖最新信息、外部文档、当前新闻或知识截止之后的事实时，可使用 `WebSearch`
2. 搜索查询应尽量具体，必要时包含产品名、版本号、年份或站点限定词
3. 若搜索结果已足以支持回答，可直接回答
4. 使用搜索结果回答时，最终答复必须包含 `Sources`
5. 只有在后续实现 `WebExtract` 后，才允许在搜索结果摘要不足时继续精读页面正文

### 10.2 `Sources` 要求

这条规则建议同时写在两个地方：

- 工具 description
- 系统提示词 / 回答规范

原因是它属于“最终回答格式要求”，不应只依赖工具描述单点约束。

## 11. 对评测体系的影响

### 11.1 为什么这套设计更利于 trajectory 与 benchmark

采用 provider-neutral 且原子化的工具设计，对后续评估更有利：

- 能清楚区分“有没有使用联网能力”
- 能分析搜索 query 是否合理
- 能统计域名过滤是否命中预期
- 能检查最终回答是否附带来源
- 后续加入 `WebExtract` 后，也能分析“粗读”和“精读”的切换路径

### 11.2 建议新增的轨迹信号

在 trajectory 或 eval 中，后续可重点关注以下信号：

- 是否调用 `WebSearch`
- `query` 是否足够具体
- 是否使用了 `allowed_domains` / `blocked_domains`
- 最终回答是否包含 `Sources`
- 回答中引用的 URL 是否来自该次搜索结果

后续如果实现 `WebExtract`，再增加：

- 是否从 `WebSearch` 命中结果进入 `WebExtract`
- 被提取的 URL 是否属于高质量来源

## 12. 实施建议

### Step 1

先实现 `WebSearch` 工具类与 provider adapter。

建议模块形态：

```text
agent_system/
  tools/
    web_search_tool.py
  integrations/
    tavily_client.py
```

### Step 2

把 `WebSearch` 注册进现有 `ToolRegistry`。

### Step 3

在系统提示词中加入联网搜索的使用条件与 `Sources` 规则。

### Step 4

为 `WebSearch` 增加最小测试：

- 参数 schema
- provider 调用映射
- 返回归一化
- 错误处理

### Step 5

在 benchmark 任务中补 1 到 2 个需要最新外部信息的任务，验证联网能力是否真实提升回答质量或可用性。

## 13. 本阶段明确不做

当前阶段不做：

- `WebExtract` 实现
- `crawl` / `map` 工具
- `research` 工具
- 多 provider fallback
- 自动 provider 路由
- 搜索结果缓存层
- 外部联网能力的 MCP 化

## 14. 最终建议

当前项目最稳的演进路径是：

```text
Phase A:
  先做 provider-neutral 的 WebSearch

Phase B:
  根据真实需求再补 WebExtract

Phase C:
  如确有平台化需求，再考虑将联网能力抽为 MCP server
```

这样可以同时兼顾：

- 开发速度
- 工具语义稳定性
- 后续 provider 可替换性
- trajectory / benchmark 的可解释性

对于当前阶段来说，这是成本最低且最不容易走偏的路线。
