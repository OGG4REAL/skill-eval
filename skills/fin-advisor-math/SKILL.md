---
name: fin-advisor-math
description: 专门用于投顾场景的数学计算技能，处理定投测算、年化收益率(CAGR)、年限反推（达到目标需要多少年）、最大回撤及夏普比率等金融运算。当用户涉及投资理财咨询、定投计划制定或历史业绩分析时使用。
metadata:
  version: 5.0.0
  dependencies: python>=3.8, numpy
---

# 投顾数学计算器 (Financial Advisor Math)

本技能通过 **CLI 脚本** 提供金融计算 API。核心逻辑封装在 `scripts/finance_formulas.py` 中。

## 🚦 执行策略 (EXECUTION STRATEGY)

本技能的核心函数库位于 `scripts/finance_formulas.py`，支持两种使用方式。
**判断规则**：CLI 内置 `--type` 能覆盖 → Tier 1；否则 → Tier 2。

### Tier 1：CLI 直接调用（标准场景）

内置计算类型能覆盖的场景，一行 Bash 完成：

```
Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type <TYPE> <ARGS>")
```

脚本输出 JSON 结果，无需写任何代码。详见下方「CLI 命令速查表」。

### Tier 2：组合扩展（复杂场景）

当 CLI 内置 type 无法覆盖需求时（如多方案对比、组合多种计算、自定义逻辑），按以下工作流操作：

1. **Read**：先读源码了解可用函数
   ```
   Read("skills/fin-advisor-math/scripts/finance_formulas.py")
   ```

2. **Write**：编写组合脚本，**import 已有函数**而非从零实现
   ```
   Write("temp/multi_rate_compare.py", code)
   ```

3. **Bash**：执行脚本
   ```
   Bash("python temp/multi_rate_compare.py")
   ```

**关键原则**：你写的是"编排代码"（循环、组合、格式化），计算的核心逻辑必须 import 已有函数完成。

**Tier 2 示例**（多收益率对比）：

```python
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
```

### ❌ 反模式（禁止）

- ❌ CLI 能覆盖的场景却自己写代码（浪费 token，不如一行 CLI）
- ❌ 不看已有函数就从头实现计算逻辑（重复造轮子，且可能算错）
- ❌ 使用 python -c 内联代码（无法审计追溯）
- ❌ 重新实现已有函数已覆盖的计算功能

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
| **内部收益率** | `irr` | `--cashflows` | `--type irr --cashflows "-10000,-10000,-10000,35000"` |

**可选参数**：
- `--freq`: 频率 (`monthly`/`weekly`/`yearly`)，默认 `monthly`
- `--rf`: 无风险利率，默认 `0.02`

---

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

---

## ⚡ 场景示例 (Tier 1 直接复制)

### 示例 1：定投终值计算
**用户问题**：每月定投 3000 元，年化 8%，10 年后有多少钱？

```
Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type aip --pmt 3000 --rate 0.08 --periods 120")
```

### 示例 2：年限反推
**用户问题**：30 万本金，年化 8%，多久能变成 100 万？

```
Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type years --pv 300000 --target 1000000 --rate 0.08")
```

### 示例 3：目标反推每期投入
**用户问题**：想 20 年后有 200 万，年化 6%，每月应该投多少？

```
Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type pmt --target 2000000 --rate 0.06 --periods 240")
```

### 示例 4：年化收益率计算
**用户问题**：3 年前投了 10 万，现在变成 15 万，年化是多少？

```
Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type cagr --pv 100000 --fv 150000 --years 3")
```

### 示例 5：内部收益率计算
**用户问题**：每月投入 1 万，连续 3 个月，最后拿到 3.5 万，实际收益率是多少？

```
Bash("python skills/fin-advisor-math/scripts/finance_formulas.py --type irr --cashflows \"-10000,-10000,-10000,35000\"")
```

---

## 📊 可视化规则 (VISUALIZATION RULE)

**⚠️ 此 Skill 仅负责计算，不负责展示！**

- ❌ **禁止**：使用 `matplotlib`、`seaborn`、`plt.savefig()` 生成图片
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
