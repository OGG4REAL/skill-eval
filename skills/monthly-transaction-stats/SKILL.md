---
name: monthly-transaction-stats
description: 专门用于银行交易数据的月度统计分析。当用户需要分析银行流水的月度趋势、业务收支、总收支或现金流水时使用此 skill。适用于已分类的银行交易 CSV 文件（bank_transactions_labeled.csv）。
---

# Monthly Transaction Stats

## Overview

本 skill 提供银行交易数据的月度统计分析功能，能够从预分类的银行流水数据中提取三个维度的月度统计信息：业务收支统计、总收支汇总和现金流水分析。所有计算通过 Python 脚本完成，输出 JSON 格式的结构化结果，便于进一步的数据可视化和分析。

## Quick Start

当用户提出以下类型的需求时，使用此 skill：

- "帮我分析这个银行账户的月度交易统计"
- "统计账户的月度业务收入和支出"
- "查看每月的总收入和总支出"
- "分析现金流水情况"
- "生成月度交易报表"

## Core Capabilities

### 1. 业务收支统计 (Business Credits and Debits)

按月统计业务类交易，包括以下类型：
- BUSINESS（经营往来）
- NEFT（国家电子资金转账）
- RTGS（大额实时结算）
- IMPS（即时支付服务）
- UPI（统一支付接口）
- POS（POS 机刷卡消费）
- CHEQUE（支票交易）
- TRF_OUT（对外转账）
- TRF_IN（收款）

**统计指标：**
- 业务收入笔数和总额
- 业务支出笔数和总额

### 2. 总收支汇总 (Gross Transaction Totals)

按月统计所有交易（不区分交易类型）。

**统计指标：**
- 总收入笔数和金额
- 总支出笔数和金额
- 月净现金流（总收入 - 总支出）

### 3. 现金流水分析 (Cash Flow Analysis)

按月统计现金类交易，包括以下类型：
- CASH_DEPOSIT（现金存入）
- CASH_WITHDRAWAL（现金取出）
- ATM（ATM 取款）
- CASH_PICKUP（现金代收服务）

**统计指标：**
- 现金存款笔数和总额
- 现金取款笔数和总额
- 现金交易占比（当月现金笔数 / 当月总笔数）

## Workflow

### Step 1: 确认输入文件

检查输入文件路径和格式：
- 默认路径：`sessions/bank_transactions_labeled.csv`
- 文件必须包含预分类的 `TXN_TYPE` 字段
- 日期字段格式：YYYY-MM-DD

### Step 2: 确定账户范围

- 默认分析第一个账户
- 支持通过命令行参数指定特定账户号
- 运行命令：`python scripts/monthly_stats.py [input_file] [account_no]`

### Step 3: 执行统计脚本

使用 `Bash` 工具执行统计脚本：

```python
Bash("python output/monthly-transaction-stats/scripts/monthly_stats.py sessions/bank_transactions_labeled.csv")
```

或指定账户号：

```python
Bash("python output/monthly-transaction-stats/scripts/monthly_stats.py sessions/bank_transactions_labeled.csv 'ACCOUNT_NUMBER'")
```

### Step 4: 解析输出结果

脚本输出 JSON 格式的结果，包含三个独立数组：

```json
{
  "account_no": "账户号",
  "business_credits_debits": [...],
  "gross_transaction_totals": [...],
  "cash_flow_analysis": [...]
}
```

### Step 5: 展示结果（可选）

根据用户需求，使用以下工具展示结果：

- **表格展示**: 使用 `render_table` 展示详细的月度数据
- **图表展示**: 使用 `render_chart` 创建趋势图或对比图
- **文本总结**: 提供关键指标的文本说明

## Data Format

### 输入数据字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| Account No | string | 账户号 |
| DATE | datetime | 交易日期 |
| TRANSACTION DETAILS | string | 交易描述 |
| TXN_TYPE | string | 交易类型标签 |
| VALUE DATE | datetime | 起息日 |
| CHQ.NO. | float | 支票号 |
| WITHDRAWAL AMT | float | 支出金额 |
| DEPOSIT AMT | float | 收入金额 |
| BALANCE AMT | float | 交易后余额 |

### 输出数据结构

每个统计维度按月输出，包含以下字段：

**业务收支统计：**
- `month`: YYYY-MM 格式的月份
- `business_income_count`: 业务收入笔数
- `business_income_total`: 业务收入总额（INR，保留2位小数）
- `business_expense_count`: 业务支出笔数
- `business_expense_total`: 业务支出总额（INR，保留2位小数）

**总收支汇总：**
- `month`: YYYY-MM 格式的月份
- `total_income_count`: 总收入笔数
- `total_income_total`: 总收入金额（INR，保留2位小数）
- `total_expense_count`: 总支出笔数
- `total_expense_total`: 总支出金额（INR，保留2位小数）
- `net_cash_flow`: 月净现金流（INR，保留2位小数）

**现金流水分析：**
- `month`: YYYY-MM 格式的月份
- `cash_deposit_count`: 现金存款笔数
- `cash_deposit_total`: 现金存款总额（INR，保留2位小数）
- `cash_withdrawal_count`: 现金取款笔数
- `cash_withdrawal_total`: 现金取款总额（INR，保留2位小数）
- `cash_transaction_ratio`: 现金交易占比（百分比，保留2位小数）

## Usage Examples

### 示例 1：分析默认账户的月度统计

用户请求："帮我分析这个银行账户的月度交易统计"

执行步骤：
1. 运行统计脚本
2. 解析 JSON 结果
3. 使用 `render_table` 展示三个维度的数据

### 示例 2：查看业务收支趋势

用户请求："显示业务收入和支出的月度趋势"

执行步骤：
1. 运行统计脚本
2. 提取 `business_credits_debits` 数据
3. 使用 `render_chart` 创建折线图或柱状图

### 示例 3：分析现金流水情况

用户请求："分析现金存取款情况"

执行步骤：
1. 运行统计脚本
2. 提取 `cash_flow_analysis` 数据
3. 使用 `render_table` 和 `render_chart` 展示现金交易详情

## Resources

### scripts/

**monthly_stats.py**
核心统计脚本，执行以下功能：
- 加载和解析银行交易 CSV 数据
- 按账户过滤数据
- 计算三个维度的月度统计
- 输出 JSON 格式的结果

**使用方法：**
```python
Bash("python monthly_stats.py [input_file] [account_no]")
```

**参数说明：**
- `input_file`:（可选）输入 CSV 文件路径，默认为 `sessions/bank_transactions_labeled.csv`
- `account_no`:（可选）要分析的账户号，默认为第一个账户

### references/

**data_schema.md**
数据字段和 TXN_TYPE 分类的详细说明文档，包含：
- 数据集概述
- 字段定义
- TXN_TYPE 分类（业务类、现金类、其他）
- 收入/支出判断规则
- 统计维度说明
- 输出格式规范

在需要确认字段定义或分类规则时，加载此文档作为参考。

## Important Notes

- **金额单位**: 所有金额为 INR，保留 2 位小数
- **缺失值处理**: 某月某分类无交易时，对应字段输出 0
- **月份格式**: 输出中的月份格式为 YYYY-MM
- **账户过滤**: 默认分析第一个账户，但支持指定账户号
- **日期格式**: 输入数据的日期字段必须为 YYYY-MM-DD 格式
- **TXN_TYPE**: 输入数据必须包含预分类的 TXN_TYPE 字段，skill 不负责重新分类
- **输出责任**: Skill 只负责计算和输出 JSON 结果，数据展示由 Agent 根据用户需求决定使用何种工具（render_table、render_chart 或文本回复）