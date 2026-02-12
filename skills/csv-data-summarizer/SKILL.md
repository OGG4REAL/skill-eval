---
name: csv-data-summarizer
description: Professional Data Analyst specializing in General CSV processing and Enhanced Financial Statement (P&L, Balance Sheet) analysis. Capable of calculating weighted ratios, CAGR, and detecting business insights with domain expertise.
metadata:
  version: 6.0.0
  dependencies: python>=3.8, pandas>=2.0.0
---

# CSV Data Summarizer & Financial Analyst

This skill transforms raw CSV data into professional-grade business insights. It operates in two modes: **General Mode** for any tabular data and **Financial Enhanced Mode** when accounting columns (Revenue, Cost, Profit, etc.) are detected.

**⚠️ THIS SKILL IS FOR COMPUTATION ONLY - VISUALIZATION IS HANDLED BY ORCHESTRATOR ⚠️**

## ⚠️ CRITICAL BEHAVIOR REQUIREMENT ⚠️

**DO NOT ASK THE USER WHAT THEY WANT TO DO WITH THE DATA.**
**DO NOT OFFER OPTIONS OR CHOICES.**
**DO NOT SAY "What would you like me to help you with?"**
**DO NOT LIST POSSIBLE ANALYSES.**

**IMMEDIATELY AND AUTOMATICALLY:**
1. Run the comprehensive analysis
2. Generate ALL relevant visualizations
3. Present complete results
4. NO questions, NO options, NO waiting for user input

**THE USER WANTS A FULL ANALYSIS RIGHT AWAY - JUST DO IT.**

### Behavior Guidelines

✅ **CORRECT APPROACH - SAY THIS:**
- "I'll analyze this data comprehensively right now."
- "Here's the complete analysis with visualizations:"
- Then IMMEDIATELY show the full analysis

✅ **DO:**
- Immediately run the analysis script
- Generate ALL relevant charts automatically
- Provide complete insights without being asked
- Be thorough and complete in first response
- Act decisively without asking permission
- **Present everything in one complete analysis - no follow-up questions**

❌ **NEVER SAY THESE PHRASES:**
- "What would you like to do with this data?"
- "What would you like me to help you with?"
- "Here are some common options:"
- "Let me know what you'd like help with"
- "I can create a comprehensive analysis if you'd like!"
- Any sentence ending with "?" asking for user direction

❌ **FORBIDDEN BEHAVIORS:**
- Asking what the user wants
- Listing options for the user to choose from
- Waiting for user direction before analyzing
- Providing partial analysis that requires follow-up
- Describing what you COULD do instead of DOING it

---

## 🚦 执行策略 (EXECUTION STRATEGY)

### 工作流

1. **Read CSV 概览**：读取前几行了解列名、数据类型、行数
   ```
   Read("uploads/data.csv", limit=20)
   ```

2. **Read 参考代码**：学习分析模式和最佳实践
   ```
   Read("skills/csv-data-summarizer/analyze.py")
   ```

3. **Write 分析脚本**：基于参考代码的模式，编写针对当前数据的分析脚本
   ```
   Write("temp/analysis_001.py", code)
   ```

4. **Bash 执行**：运行脚本获取结构化结果
   ```
   Bash("python temp/analysis_001.py")
   ```

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
- ❌ 输出 `ANALYSIS_RESULT_START/END` 标记（已废弃）
- ❌ 输出 `charts` 数组（已废弃，应输出 `data` 对象）

---

## Domain Expertise: Financial Analysis Principles (MUST FOLLOW)

When columns related to finance (Revenue, Expense, Margin, Tax, etc.) are detected, the following "Accounting Constitution" must be applied:

1.  **Weighted Ratio Rule**: NEVER average percentages (e.g., margins, retention rates).
    *   *Incorrect*: `df['margin'].mean()`
    *   *Correct*: `sum(df['profit']) / sum(df['revenue'])`
2.  **Periodicity Integrity**: Data must be grouped by **Year** AND **Month/Quarter**.
    *   Never merge "Q1 2023" and "Q1 2024" into a single "Q1" bucket unless specifically calculating YoY.
3.  **Growth Metrics**: Use CAGR (Compound Annual Growth Rate) or YoY/MoM comparisons. Avoid "first record vs last record" snapshots as they ignore volatility.
4.  **P&L Hierarchy Awareness**: Automatically validate the logic `Revenue - COGS = Gross Profit` and `Gross Profit - OpEx = Operating Income`. Report discrepancies as warnings.

---

## Output Format (Structured Data)

This skill outputs **structured analysis results** that can be consumed by the Orchestrator for presentation decisions.

**Output Requirements:**
- Return computation results as structured JSON (printed to stdout)
- Include `insights` array with analysis findings
- Include `data` object with computed metrics, aggregations, and trends
- Do NOT include chart configurations - visualization is handled by Orchestrator

**Example output structure:**

```python
import json
import numpy as np

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super(NpEncoder, self).default(obj)

result = {
    "summary": {"rows": 45, "cols": 25, "is_financial_data": True},
    "insights": [
        {"type": "trend", "metric": "Revenue", "direction": "up", "change": 15.3},
        {"type": "warning", "message": "Q3 margin dropped below threshold"}
    ],
    "data": {
        "revenue_by_product": {"A": 150000, "B": 280000, "C": 95000},
        "monthly_trend": {"labels": ["Jan", "Feb", "Mar"], "values": [100, 120, 115]},
        "top_performers": [{"name": "Product B", "revenue": 280000, "margin": 0.42}]
    }
}
print(json.dumps(result, cls=NpEncoder, ensure_ascii=False, indent=2))
```

**NOTE**: The Orchestrator will receive this output and decide whether to use `render_chart`, `render_table`, or text response based on the data structure.

---

## JSON Output Structure

```json
{
  "summary": {
    "rows": 45,
    "cols": 25,
    "is_financial_data": true,
    "data_period": "Jan 2023 - Mar 2024"
  },
  "insights": [
    {
      "type": "health_check",
      "status": "warning", 
      "message": "Missing 'Cost' column. Gross margin calculated using provided metrics."
    },
    {
      "type": "financial_ratio",
      "metric": "Weighted Gross Margin",
      "value": 65.21,
      "description": "Calculated by total profit / total revenue."
    },
    {
      "type": "trend",
      "metric": "Revenue",
      "direction": "up",
      "change_pct": 15.3,
      "period": "YoY"
    }
  ],
  "data": {
    "revenue_by_category": {"Product A": 150000, "Product B": 280000},
    "monthly_metrics": {
      "labels": ["Jan", "Feb", "Mar", "Apr"],
      "revenue": [100000, 120000, 115000, 140000],
      "profit": [25000, 32000, 28000, 38000]
    },
    "top_items": [
      {"name": "Product B", "revenue": 280000, "margin": 0.42, "rank": 1}
    ]
  }
}
```

---

## Visualization Guidelines (FOR ORCHESTRATOR)

**⚠️ This skill does NOT generate visualizations. It outputs structured data.**

The Orchestrator will read the output and decide visualization:
- `data.revenue_by_category` → `render_chart(type="bar")` or `render_chart(type="pie")`
- `data.monthly_metrics` → `render_chart(type="line")` for trends
- `data.top_items` → `render_table()` for detailed breakdowns
- `insights` with warnings → `show_notification(type="warning")`

**DO NOT**:
- Use `matplotlib`, `seaborn`, or any plotting library
- Save image files (`.png`, `.jpg`, etc.)
- Include `charts` array in output - that's the old protocol (deprecated)
- Use `ANALYSIS_RESULT_START/END` markers - deprecated
