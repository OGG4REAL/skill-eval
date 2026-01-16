---
name: fin-advisor-math
description: 专门用于投顾场景的数学计算技能，处理定投测算、年化收益率(CAGR)、年限反推（达到目标需要多少年）、最大回撤及夏普比率等金融运算。当用户涉及投资理财咨询、定投计划制定或历史业绩分析时使用。
metadata:
  version: 4.0.0
  dependencies: python>=3.8, numpy
---

# 投顾数学计算器 (Financial Advisor Math)

本技能通过 **CLI 脚本** 提供金融计算 API。核心逻辑封装在 `scripts/finance_formulas.py` 中。

## 🚦 执行策略 (EXECUTION STRATEGY)

### ⚡ 优先：CLI 直接执行
**99% 的场景使用此方式，直接调用 bash 工具执行脚本：**

```bash
bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type <TYPE> <ARGS>")
```

脚本会直接输出 JSON 结果，**无需读取源码，无需写 Python 代码**。

### 🔧 备选：run_python_code
仅当以下情况使用：
- 需要多函数组合计算（如对比 + 生成图表数据）
- 脚本 CLI 不支持的特殊场景
- 用户明确要求自定义逻辑

---

## 📚 CLI 命令速查表

脚本路径：`skills/fin-advisor-math/scripts/finance_formulas.py`

| 计算类型 | --type | 必需参数 | 示例命令 |
|----------|--------|----------|----------|
| **定投终值** | `aip` | `--pmt --rate --periods` | `--type aip --pmt 3000 --rate 0.08 --periods 120` |
| **一次性投资** | `lump` | `--pv --rate --periods` | `--type lump --pv 100000 --rate 0.08 --periods 12` |
| **年化收益率** | `cagr` | `--pv --fv --years` | `--type cagr --pv 100000 --fv 150000 --years 3` |
| **年限反推** | `years` | `--pv --target --rate` | `--type years --pv 300000 --target 1000000 --rate 0.08` |
| **目标反推投入** | `pmt` | `--target --rate --periods` | `--type pmt --target 2000000 --rate 0.06 --periods 240` |
| **最大回撤** | `mdd` | `--nav` | `--type mdd --nav "1.0,1.1,0.95,1.2,0.8"` |
| **夏普比率** | `sharpe` | `--returns` | `--type sharpe --returns "0.05,0.02,-0.01,0.03"` |

**可选参数**：
- `--freq`: 频率 (`monthly`/`weekly`/`yearly`)，默认 `monthly`
- `--rf`: 无风险利率，默认 `0.02`

---

## ⚡ 场景示例 (直接复制)

### 示例 1：定投终值计算
**用户问题**：每月定投 3000 元，年化 8%，10 年后有多少钱？

```
bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type aip --pmt 3000 --rate 0.08 --periods 120")
```

### 示例 2：年限反推
**用户问题**：30 万本金，年化 8%，多久能变成 100 万？

```
bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type years --pv 300000 --target 1000000 --rate 0.08")
```

### 示例 3：目标反推每期投入
**用户问题**：想 20 年后有 200 万，年化 6%，每月应该投多少？

```
bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type pmt --target 2000000 --rate 0.06 --periods 240")
```

### 示例 4：年化收益率计算
**用户问题**：3 年前投了 10 万，现在变成 15 万，年化是多少？

```
bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type cagr --pv 100000 --fv 150000 --years 3")
```

---

## 🔧 复杂场景：使用 run_python_code

当需要**对比多个方案**时，使用 `run_python_code` 进行**纯计算**：

```python
import sys
sys.path.insert(0, '/workspace/skills/fin-advisor-math/scripts')
from finance_formulas import calc_years_to_target, calc_aip_fv
import json

# 多收益率对比（纯计算）
rates = [0.06, 0.08, 0.10, 0.12]
results = []
for r in rates:
    years = calc_years_to_target(pv=300000, target_fv=1000000, annual_rate=r)
    results.append({"rate": f"{r*100:.0f}%", "years": round(years, 1)})

# 输出计算结果（结构化数据）
print(json.dumps(results, ensure_ascii=False, indent=2))
```

**输出示例：**
```json
[
  {"rate": "6%", "years": 15.7},
  {"rate": "8%", "years": 11.9},
  {"rate": "10%", "years": 9.6},
  {"rate": "12%", "years": 8.0}
]
```

---

## 📊 可视化规则 (VISUALIZATION RULE)

**⚠️ 此 Skill 仅负责计算，不负责展示！**

- ❌ **禁止**：使用 `matplotlib`、`seaborn`、`plt.savefig()` 生成图片
- ❌ **禁止**：构建 `ANALYSIS_RESULT_START/END` 协议或手动构建 JSON 图表数据
- ✅ **正确**：输出结构化计算结果（JSON/数值），让 **Orchestrator** 决定如何展示

**Orchestrator 的职责**：
当计算结果适合可视化时，Orchestrator 会调用 `render_chart` 或 `render_table` 等 UI 工具：
- 单一计算 → 文本回复
- 多方案对比 → `render_chart` (bar)
- 趋势分析 → `render_chart` (line)
- 详细数据表 → `render_table`

---

## 📝 风险提示

所有计算结果展示后，**必须附带以下风险提示**：

> 测算结果仅供参考，不代表未来实际收益。投资有风险，入市需谨慎。
