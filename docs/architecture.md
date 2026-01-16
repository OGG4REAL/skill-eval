 # Claude Skills Agent 架构设计文档
 
 ## 📖 项目概述
 
 **Claude Skills Agent** 是一个深度对齐 Claude 官方 Skills 设计理念的智能 Agent 系统。通过 **Bash Runtime**（自主探索）与 **E2B Code Interpreter**（代码执行）的有机结合，实现了类似 Claude 官方"分析师"或"工程师"技能的高级功能。
 
 ### 核心特性
 - ✅ **Bash Runtime**：Agent 通过 bash 命令自由探索文件系统
 - ✅ **E2B 云沙盒**：持久化的远程代码执行环境
 - ✅ **自主学习**：Agent 主动读取文档和参考代码
 - ✅ **三层加载**：元数据 → SKILL.md → 参考代码
 - ✅ **多轮记忆**：智能对话历史压缩与管理
 - ✅ **前后端分离**：FastAPI + React 的现代化架构
 
 ---
 
 ## 1. 核心设计哲学：为什么选择 Bash Runtime？
 
 ### 1.1 传统 Function Calling 的局限性
 
 传统的 Agent 系统通常采用硬编码的 API 调用（Function Calling）：
 
 ```python
 # 传统方式：需要为每个操作定义一个函数
 def read_csv_schema(file_path: str) -> dict:
     """预定义的工具：读取 CSV 表头"""
     return pd.read_csv(file_path).columns.tolist()
 
 def get_skill_description(skill_name: str) -> str:
     """预定义的工具：获取技能描述"""
     return load_skill_metadata(skill_name)
 ```
 
 **问题**：
 - ❌ **灵活性差**：每个新需求都需要开发新工具
 - ❌ **无法探索**：Agent 无法自由查看文件系统
 - ❌ **学习受限**：无法主动阅读参考代码和注释
 
 ### 1.2 Bash Runtime 的优势
 
 本项目采用 Claude 官方的 Bash Runtime 设计：
 
 ```python
 # Bash Runtime：Agent 自由探索
 bash("ls skills/")                           # 查看有哪些技能
 bash("cat skills/csv-data-summarizer/SKILL.md")  # 阅读技能文档
 bash("head -20 data.csv")                    # 预览数据结构
 bash("grep 'margin' analyze.py")             # 搜索关键代码
 ```
 
 **优势**：
 - ✅ **完全自由**：Agent 可以探索任何文件
 - ✅ **主动学习**：Agent 自己决定读取哪些文档
 - ✅ **快速迭代**：无需为每个操作定义新工具
 - ✅ **对齐官方**：完全符合 Claude Skills 的设计理念
 
 ---
 
 ## 2. Bash Runtime 实现细节
 
 ### 2.1 跨平台兼容性
 
 为了在 Windows/Linux/Mac 上保持一致行为，我们用 Python 实现了常用的 Bash 命令：
 
 ```python
 # agent_system/tools/bash_runtime.py
 
 class BashRuntimeTool(BaseTool):
     """Python 实现的 Bash 命令，跨平台兼容"""
     
     def execute(self, command: str) -> str:
         """执行 bash 命令"""
         parts = shlex.split(command)
         cmd = parts[0]
         args = parts[1:]
         
         # 路由到对应的处理函数
         if cmd == "cat":
             return self._cat(args)
         elif cmd == "ls":
             return self._ls(args)
         elif cmd == "head":
             return self._head(args)
         elif cmd == "grep":
             return self._grep(args)
         # ... 更多命令
 ```
 
 ### 2.2 Agent 的探索流程
 
 当用户说"分析 showcase_financial_pl_data.csv"时，Agent 的执行轨迹：
 
 ```
 → 第1轮思考
   LLM: "我需要先了解有哪些可用的分析工具"
   调用: bash("ls skills/")
   返回: csv-data-summarizer/  docx/
 
 → 第2轮思考
   LLM: "csv-data-summarizer 看起来合适，让我读取它的使用说明"
   调用: bash("cat skills/csv-data-summarizer/SKILL.md")
   返回: [完整的技能文档，包括财务分析标准]
 
 → 第3轮思考
   LLM: "文档提到有参考代码 analyze.py，我需要学习其实现"
   调用: bash("cat skills/csv-data-summarizer/analyze.py")
   返回: [参考代码，包含加权平均计算、CAGR 等]
 
 → 第4轮思考
   LLM: "现在我知道怎么做了，先看看数据结构"
   调用: bash("head -20 showcase_financial_pl_data.csv")
   返回: [CSV 前20行]
 
 → 第5轮思考
   LLM: "好的，我可以基于学到的模式写分析代码了"
   调用: run_python_code(
     code="""
     import pandas as pd
     import json
     
     # 读取数据
     df = pd.read_csv('showcase_financial_pl_data.csv')
     
     # 按照 analyze.py 学到的方法计算加权毛利率
     total_revenue = df['total_revenue'].sum()
     total_profit = df['gross_profit'].sum()
     weighted_margin = (total_profit / total_revenue) * 100
     
     # 输出结构化 JSON
     result = {
         "summary": {"weighted_gross_margin": weighted_margin},
         "charts": [...]
     }
     print("ANALYSIS_RESULT_START")
     print(json.dumps(result, indent=2))
     print("ANALYSIS_RESULT_END")
     """,
     input_files=["showcase_financial_pl_data.csv"]
   )
 
 ✓ 任务完成！
 ```
 
 ### 2.3 为什么这种方式更强大？
 
 **对比传统方式：**
 
 | 场景 | 传统 Function Calling | Bash Runtime (本系统) |
 |------|---------------------|---------------------|
 | Agent 想了解技能列表 | 需要预定义 `list_skills()` 工具 | `bash("ls skills/")` |
 | Agent 想读取文档 | 需要预定义 `read_skill_doc(name)` | `bash("cat skills/xxx/SKILL.md")` |
 | Agent 想预览 CSV 前几行 | 需要预定义 `preview_csv(file, n)` | `bash("head -20 data.csv")` |
 | Agent 想搜索关键字 | 需要预定义 `search_file(file, keyword)` | `bash("grep 'margin' analyze.py")` |
 | Agent 想查看文件大小 | 需要预定义 `get_file_info(file)` 工具 | `bash("wc -l data.csv")` |
 
 Bash Runtime 让 Agent 拥有了**几乎无限的探索能力**，而无需为每个小需求定义新工具。
 
 ---
 
 ## 3. E2B Code Interpreter：云端持久化沙盒
 
 ### 3.1 为什么选择 E2B？
 
 **E2B** (Extensible Execution Backend) 是一个专为 AI Agent 设计的云端代码执行环境：
 
 - ✅ **远程执行**：无需本地 Docker，降低部署复杂度
 - ✅ **持久化会话**：一次对话中安装的依赖和生成的变量会保留
 - ✅ **安全隔离**：每个会话独立沙盒，防止代码污染
 - ✅ **自动管理**：文件上传、依赖安装、输出下载全自动
 
 ### 3.2 与 Bash Runtime 的配合
 
 ```
 ┌─────────────────────────────────────────────────────────┐
 │  Agent (DeepSeek LLM)                                   │
 │  - 通过 bash 命令探索本地文件系统                        │
 │  - 读取 SKILL.md 和 analyze.py 学习                     │
 │  - 决定执行策略                                          │
 └─────────────────────────────────────────────────────────┘
                       │
                       │ bash("cat ...") 
                       │ bash("ls ...")
                       ▼
 ┌─────────────────────────────────────────────────────────┐
 │  本地文件系统                                            │
 │  - skills/                                              │
 │  - sessions/{session_id}/uploads/                       │
 │  - showcase_financial_pl_data.csv                       │
 └─────────────────────────────────────────────────────────┘
                       │
                       │ run_python_code(code, input_files)
                       ▼
 ┌─────────────────────────────────────────────────────────┐
 │  E2B 云端沙盒 (Python 3.11)                             │
 │  - 自动上传 input_files                                  │
 │  - 执行 Agent 生成的 Python 代码                         │
 │  - 捕获 stdout/stderr                                    │
 │  - 检测生成的文件 (*.png, *.json, *.xlsx)               │
 └─────────────────────────────────────────────────────────┘
                       │
                       │ 自动下载生成文件
                       ▼
 ┌─────────────────────────────────────────────────────────┐
 │  本地输出目录                                            │
 │  - sessions/{session_id}/output/                        │
 │    ├── revenue_trend.png                                │
 │    ├── margin_analysis.png                              │
 │    └── financial_summary.json                           │
 └─────────────────────────────────────────────────────────┘
 ```
 
 ### 3.3 持久化会话的威力
 
 **场景：多步骤数据处理**
 
 ```python
 # 第1轮对话：用户上传 large_dataset.zip
 User: "先解压这个数据集"
 
 → Agent: run_python_code("""
     import zipfile
     with zipfile.ZipFile('large_dataset.zip', 'r') as z:
         z.extractall('data/')
     print("✓ 解压完成，共", len(os.listdir('data/')), "个文件")
 """)
 
 # 第2轮对话：用户请求数据清洗
 User: "清洗数据，删除空值行"
 
 → Agent: run_python_code("""
     import pandas as pd
     df = pd.read_csv('data/raw.csv')  # 沙盒中文件依然存在！
     df_clean = df.dropna()
     df_clean.to_csv('data/clean.csv', index=False)
     print(f"✓ 清洗完成，从 {len(df)} 行减少到 {len(df_clean)} 行")
 """)
 
 # 第3轮对话：用户请求可视化
 User: "生成销售趋势图"
 
 → Agent: run_python_code("""
     import pandas as pd
     import matplotlib.pyplot as plt
     
     df = pd.read_csv('data/clean.csv')  # 使用第2轮生成的文件！
     df.plot(x='date', y='sales')
     plt.savefig('sales_trend.png')
 """)
 ```
 
 **关键优势**：每一轮对话都能继承上一轮的成果，无需重复上传或计算。
 
 ---
 
 ## 4. 三层加载机制：高效的上下文管理
 
 ### 4.1 为什么需要分层加载？
 
 假设你有 50 个技能，每个技能的 `SKILL.md` 平均 2000 tokens：
 - **全量加载**：50 × 2000 = 100,000 tokens（仅技能文档就占满了上下文）
 - **分层加载**：50 × 50 tokens (元数据) = 2,500 tokens（启动时仅占 2.5K）
 
 ### 4.2 三层加载流程
 
 ```yaml
 # 第1层：元数据（总是在 System Prompt 中）
 ---
 name: csv-data-summarizer
 description: 专业财务数据分析师，擅长损益表分析和可视化
 metadata:
   version: 2.0.0
   category: financial-analysis
 ---
 ```
 
 ```markdown
 # 第2层：SKILL.md（Agent 按需读取）
 
 ## 使用方式
 1. 使用 bash 命令预览 CSV 文件结构
 2. 阅读参考代码 analyze.py 学习实现模式
 3. 运行 Python 代码生成分析结果
 
 ## 财务分析标准
 - **加权比率**：必须用总利润/总收入，禁止直接平均
 - **增长率**：使用 CAGR 或准确的 YoY 比较
 - **时间轴**：严格区分年份和季度
 ```
 
 ```python
 # 第3层：参考代码（Agent 按需读取）
 
 # skills/csv-data-summarizer/analyze.py
 
 def calculate_weighted_average_margin(df, revenue_col, profit_col):
     """
     ⚠️ 正确计算加权平均毛利率
     错误做法：df['margin_pct'].mean()  # 简单平均
     正确做法：total_profit / total_revenue  # 加权平均
     """
     total_revenue = df[revenue_col].sum()
     total_profit = df[profit_col].sum()
     return (total_profit / total_revenue) * 100
 
 # ... 更多示例代码
 ```
 
 ### 4.3 实际执行时的 Token 消耗
 
 ```
 系统启动：
   System Prompt: 1,000 tokens
   50个技能元数据: 2,500 tokens
   工具定义: 500 tokens
   ─────────────────────────────
   总计: 4,000 tokens
 
 用户请求"分析财务数据"：
   用户消息: 50 tokens
   bash("cat SKILL.md") 结果: 1,500 tokens
   bash("cat analyze.py") 结果: 2,000 tokens
   bash("head data.csv") 结果: 300 tokens
   ─────────────────────────────
   累计: 7,850 tokens
 
 执行分析：
   run_python_code 输出: 1,000 tokens
   Agent 回复: 500 tokens
   ─────────────────────────────
   总计: 9,350 tokens
 ```
 
 相比全量加载的 100K+ tokens，分层加载节省了 **90%+ 的上下文空间**。
 
 ---
 
 ## 5. 实战案例：金融数据分析师技能重构
 
 ### 5.1 重构前的问题
 
 **Agent 的"幻觉"输出**：
 ```
 平均毛利率: 63.3%  ❌ 错误！（使用了简单平均）
 收入增长: 126.67%  ❌ 错误！（时间跨度不清）
 ```
 
 **原因分析**：
 - `analyze.py` 模板使用了 `df['margin_pct'].mean()`（简单平均）
 - 没有区分周期性（跨年数据被混在一起）
 - Agent 没有财务领域知识指导
 
 ### 5.2 重构方案：领域知识注入
 
 **步骤1：更新 SKILL.md（规则注入）**
 
 ```markdown
 ## 财务分析标准（强制遵守）
 
 ### 1. 比率计算
 - **错误**：`df['gross_margin_pct'].mean()`（简单平均）
 - **正确**：`df['gross_profit'].sum() / df['total_revenue'].sum()`（加权）
 
 ### 2. 增长率计算
 - **错误**：`(last_value - first_value) / first_value`（忽略时间）
 - **正确**：使用 CAGR = `(last/first)^(1/years) - 1`
 
 ### 3. 周期性处理
 - **错误**：按 month 分组（会把不同年份的同月混在一起）
 - **正确**：按 (year, month) 或 (year, quarter) 分组
 ```
 
 **步骤2：更新 analyze.py（模板代码）**
 
 ```python
 # skills/csv-data-summarizer/analyze.py
 
 def calculate_weighted_average_margin(df, revenue_col, profit_col):
     """加权平均毛利率（财务标准）"""
     total_revenue = df[revenue_col].sum()
     total_profit = df[profit_col].sum()
     if total_revenue > 0:
         return round((total_profit / total_revenue) * 100, 2)
     return None
 
 def calculate_cagr(start_value, end_value, years):
     """复合年均增长率"""
     if start_value > 0 and years > 0:
         return round((pow(end_value / start_value, 1 / years) - 1) * 100, 2)
     return None
 
 # Agent 会学习并模仿这些函数！
 ```
 
 ### 5.3 重构后的效果
 
 **Agent 的输出（完全准确）**：
 ```
 加权毛利率: 65.22%  ✓ 正确！
 总收入: $20,651,000
 总毛利润: $13,468,100
 
 收入增长趋势:
 - 从2023年1月 $855,000 增长到 2024年3月 $1,967,000
 - 增长幅度: 130%（15个月内）
 - CAGR: 约 85% 年化增长率  ✓ 正确！
 
 季度表现:
 - Q1 2023: $2,753,000 (净利率11.7%)
 - Q2 2023: $3,375,000 (净利率12.2%)
 - Q3 2023: $4,063,000 (净利率13.1%)
 - Q4 2023: $4,853,000 (净利率13.7%)
 - Q1 2024: $5,607,000 (净利率14.2%)  ✓ 正确！
 ```
 
 ---
 
 ## 6. 前端集成：实时日志流与图表渲染
 
 ### 6.1 FastAPI 后端架构
 
 ```python
 # server/app.py
 
 @app.post("/sessions/{session_id}/messages")
 async def send_message(session_id: str, body: MessageRequest):
     """触发 Agent 分析（异步执行）"""
     # 在后台启动 Agent 进程
     subprocess.Popen([
         sys.executable, "-m", "agent_system.main",
         body.query,
         "--session-id", session_id,
         "--log", f"sessions/{session_id}/chat.log"
     ])
     return {"status": "processing"}
 
 @app.get("/sessions/{session_id}/stream")
 async def stream_logs(session_id: str):
     """实时推送 Agent 执行日志（SSE）"""
     async def event_generator():
         log_file = f"sessions/{session_id}/chat.log"
         last_pos = 0
         while True:
             if os.path.exists(log_file):
                 with open(log_file, 'r', encoding='utf-8') as f:
                     f.seek(last_pos)
                     new_lines = f.readlines()
                     last_pos = f.tell()
                     for line in new_lines:
                         yield f"data: {line}\n\n"
             await asyncio.sleep(0.5)
     
     return StreamingResponse(event_generator(), media_type="text/event-stream")
 ```
 
 ### 6.2 React 前端架构
 
 ```typescript
 // frontend/src/App.tsx
 
 const [logs, setLogs] = useState<string[]>([]);
 const [analysisResult, setAnalysisResult] = useState<any>(null);
 const jsonBufferRef = useRef("");
 const isCollectingJsonRef = useRef(false);
 
 useEffect(() => {
   // 订阅 SSE 日志流
   const eventSource = new EventSource(`/api/sessions/${sessionId}/stream`);
   
   eventSource.onmessage = (event) => {
     const line = stripAnsi(event.data);
     
     // 检测 JSON 边界标记
     if (line.trim() === "ANALYSIS_RESULT_START") {
       isCollectingJsonRef.current = true;
       jsonBufferRef.current = "";
       return;
     }
     
     if (line.trim() === "ANALYSIS_RESULT_END") {
       try {
         const result = JSON.parse(jsonBufferRef.current);
         setAnalysisResult(result);  // 触发图表渲染！
       } catch (e) {
         console.error("JSON 解析失败", e);
       }
       isCollectingJsonRef.current = false;
       return;
     }
     
     // 收集 JSON 或显示日志
     if (isCollectingJsonRef.current) {
       jsonBufferRef.current += line + "\n";
     } else {
       setLogs(prev => [...prev, line]);
     }
   };
 }, [sessionId]);
 ```
 
 ```typescript
 // frontend/src/components/ChartRenderer.tsx
 
 export default function ChartRenderer({ charts }: { charts: ChartData[] }) {
   return (
     <div className="charts-grid">
       {charts.map((chart, index) => (
         <div key={index} className="chart-container">
           <ReactECharts
             option={getEChartsOption(chart)}
             notMerge={true}
             lazyUpdate={true}
             style={{ height: '400px' }}
           />
         </div>
       ))}
     </div>
   );
 }
 ```
 
 ### 6.3 数据流向
 
 ```
 ┌─────────────────┐
 │ 用户上传 CSV    │
 │ + 发送指令      │
 └────────┬────────┘
          │
          │ POST /sessions/{id}/messages
          ▼
 ┌─────────────────────────────────────────┐
 │ FastAPI 后端                            │
 │ - 启动 Agent 进程                       │
 │ - Agent 通过 bash 读取 SKILL.md         │
 │ - Agent 通过 run_python_code 分析数据   │
 │ - 输出日志到 chat.log                   │
 │ - 输出结果 JSON（带 ANALYSIS_RESULT）   │
 └────────┬────────────────────────────────┘
          │
          │ SSE /sessions/{id}/stream
          ▼
 ┌─────────────────────────────────────────┐
 │ React 前端                              │
 │ - 实时显示日志流（左侧面板）            │
 │ - 解析 ANALYSIS_RESULT JSON             │
 │ - 渲染 ECharts 图表（右侧面板）         │
 └─────────────────────────────────────────┘
 ```
 
 ---
 
 ## 7. 核心代码导读
 
 ### 7.1 Bash Runtime 实现
 
 ```python
 # agent_system/tools/bash_runtime.py
 
 class BashRuntimeTool(BaseTool):
     """跨平台的 Bash 命令模拟器"""
     
     def _cat(self, args: List[str]) -> str:
         """读取文件内容（支持多文件）"""
         result = []
         for file_path in args:
             path = Path(file_path)
             if not path.exists():
                 result.append(f"cat: {file_path}: No such file")
                 continue
             try:
                 content = path.read_text(encoding='utf-8')
                 result.append(content)
             except Exception as e:
                 result.append(f"cat: {file_path}: {e}")
         return "\n".join(result)
     
     def _ls(self, args: List[str]) -> str:
         """列出目录内容"""
         # 支持 -la 等参数
         # 实现略...
     
     def _head(self, args: List[str]) -> str:
         """显示文件前 N 行"""
         # 实现略...
 ```
 
 ### 7.2 E2B 执行器实现
 
 ```python
 # agent_system/tools/python_executor.py
 
 class PythonExecutorTool(BaseTool):
     def execute(self, code: str, input_files: List[str] = None) -> str:
         """在 E2B 沙盒中执行 Python 代码"""
         
         # 1. 上传输入文件到沙盒
         for file in input_files:
             local_path = self._find_file(file)
             self.sandbox.upload_file(local_path)
         
         # 2. 执行代码
         execution = self.sandbox.run_code(code)
         
         # 3. 收集输出
         stdout = execution.text
         stderr = execution.error
         
         # 4. 下载生成的文件
         generated_files = self._detect_output_files(self.sandbox)
         for file in generated_files:
             self.sandbox.download_file(
                 file,
                 f"sessions/{self.session_id}/output/{file}"
             )
         
         return {
             "stdout": stdout,
             "stderr": stderr,
             "files": generated_files
         }
 ```
 
 ### 7.3 Agent 主循环
 
 ```python
 # agent_system/agent/core.py
 
 class Agent:
     def run(self, user_message: str) -> str:
         """Agent 主循环"""
         
         # 添加用户消息到历史
         self.memory.add_message("user", user_message)
         
         for iteration in range(self.max_iterations):
             # 1. 构造消息（包含压缩后的历史）
             messages = self.memory.get_messages_for_llm()
             
             # 2. 调用 LLM
             response = self.llm_client.chat(messages)
             
             # 3. 检查是否需要调用工具
             if not response.tool_calls:
                 # Agent 完成任务
                 return response.content
             
             # 4. 执行工具调用
             for tool_call in response.tool_calls:
                 tool = self.tools[tool_call.name]
                 result = tool.execute(**tool_call.arguments)
                 
                 # 记录到历史
                 self.memory.add_tool_call(
                     tool_name=tool_call.name,
                     arguments=tool_call.arguments,
                     result=result
                 )
         
         raise Exception("达到最大迭代次数")
 ```
 
 ---
 
 ## 8. 对比：本系统 vs Claude Skills 官方
 
 | 特性 | Claude Skills 官方 | 本系统 (Claude Skills Agent) | 状态 |
 |------|------------------|---------------------------|------|
 | Bash Runtime | ✅ 完整实现 | ✅ Python 跨平台实现 | ✅ 对齐 |
 | 三层加载 | ✅ 元数据 + 按需加载 | ✅ 完全相同 | ✅ 对齐 |
 | 沙盒环境 | ✅ Claude 内置沙盒 | ✅ E2B 云沙盒 | ✅ 对齐 |
 | 持久化会话 | ✅ 跨对话保持 | ✅ Session ID 绑定 | ✅ 对齐 |
 | 文件自动下载 | ✅ 自动识别 | ✅ 自动识别 | ✅ 对齐 |
 | 多轮记忆 | ✅ 自动压缩 | ✅ 智能压缩 | ✅ 对齐 |
 | 技能市场 | ✅ 官方技能库 | ⚠️ 本地技能目录 | 🔄 可扩展 |
 | 前端集成 | ✅ Claude 界面 | ✅ 自定义 React 前端 | ✅ 对齐 |
 
 ---
 
 ## 9. 快速上手
 
 ### 9.1 最小化示例
 
 ```bash
 # 1. 安装依赖
 pip install -r requirements-agent.txt
 
 # 2. 配置 API
 cp env.example .env
 # 编辑 .env 填入 DEEPSEEK_API_KEY 和 E2B_API_KEY
 
 # 3. 运行
 python -m agent_system.main "分析 showcase_financial_pl_data.csv"
 ```
 
 ### 9.2 前后端联调
 
 ```bash
 # 一键启动前后端
 python dev_server.py
 
 # 访问 http://localhost:5173
 # - 左侧：实时 Agent 思考日志
 # - 右侧：分析结果与交互图表
 ```
 
 ### 9.3 添加自定义技能
 
 ```bash
 # 1. 创建技能目录
 mkdir -p skills/my-skill
 
 # 2. 编写 SKILL.md
 cat > skills/my-skill/SKILL.md << 'EOF'
 ---
 name: my-skill
 description: 我的自定义技能
 ---
 
 ## 使用方式
 1. 使用 bash 命令探索输入文件
 2. 编写 Python 代码处理数据
 3. 生成结构化 JSON 输出
 EOF
 
 # 3. 添加参考代码（可选）
 cat > skills/my-skill/example.py << 'EOF'
 import pandas as pd
 # 你的示例代码...
 EOF
 
 # 4. 重启 Agent（自动识别新技能）
 python -m agent_system.main "使用 my-skill 处理数据"
 ```
 
 ---
 
 ## 10. 总结：为什么这个架构强大？
 
 ### 10.1 技术创新点
 
 1. **Bash Runtime**：让 Agent 拥有"阅读"和"探索"的能力，而不只是被动执行
 2. **三层加载**：极致的上下文效率，50个技能仅占用2.5K tokens
 3. **E2B 持久化**：多轮对话中沙盒环境完整保留，支持复杂任务
 4. **领域知识注入**：通过 SKILL.md + 参考代码将专业知识"编译"到 Agent 中
 5. **前后端分离**：SSE 实时日志流 + React 交互式图表
 
 ### 10.2 适用场景
 
 - ✅ **金融分析**：损益表分析、DCF 建模、敏感性分析
 - ✅ **数据处理**：CSV 清洗、格式转换、数据透视
 - ✅ **文档生成**：自动化报告、DOCX 编辑、PDF 生成
 - ✅ **代码辅助**：代码审查、重构建议、单元测试生成
 
 ### 10.3 未来扩展方向
 
 - 🔄 **多 Agent 协作**：分析师 + 工程师 + 审计师多角色协同
 - 🔄 **技能市场**：社区共享技能库，一键导入
 - 🔄 **工作流引擎**：复杂任务的 DAG 编排
 - 🔄 **持久化知识库**：Agent 从历史任务中学习
 
 ---
 
 ## 附录：关键文件索引
 
 - **核心架构**
   - `agent_system/tools/bash_runtime.py` - Bash Runtime 实现
   - `agent_system/tools/python_executor.py` - E2B 执行器
   - `agent_system/agent/core.py` - Agent 主循环
   - `agent_system/agent/memory.py` - 记忆管理
 
 - **技能系统**
   - `agent_system/skills/manager.py` - 技能加载器
   - `skills/csv-data-summarizer/SKILL.md` - 财务分析师技能定义
   - `skills/csv-data-summarizer/analyze.py` - 参考代码模板
 
 - **前后端**
   - `server/app.py` - FastAPI 后端
   - `frontend/src/App.tsx` - React 主应用
   - `frontend/src/components/ChartRenderer.tsx` - 图表渲染器
 
 - **配置**
   - `.env` - API 密钥和系统配置
   - `requirements-agent.txt` - Python 依赖
 
 ---
 
 **💡 核心理念**：不要教 AI 如何做，而是提供环境（Bash）、计算引擎（E2B）和知识库（SKILL.md + 参考代码），让 AI 自己学会如何做。
 
 **🚀 Enjoy building with Claude Skills Agent!**
