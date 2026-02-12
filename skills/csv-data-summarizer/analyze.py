"""
CSV 数据分析参考实现 (Reference Implementation)

本脚本是 csv-data-summarizer skill 的参考代码，供 Agent Read 后学习分析模式。
主要演示以下最佳实践：
- NpEncoder：处理 numpy 类型的 JSON 序列化
- 金融列检测：通过关键词匹配识别 Revenue/Profit/Margin 等列
- 加权比率计算：total_profit / total_revenue 而非 df['margin'].mean()
- pandas 惯用法：groupby、agg、sort_values 等数据处理模式

输出格式：
- summary: 数据概览（行数、列数、是否金融数据）
- insights: 分析发现（类型、指标、变化）
- data: 结构化数据（供 Orchestrator 决策可视化方式）

注意：本脚本输出纯数据结构，不包含图表配置。可视化由前端 ECharts 负责。
"""
import pandas as pd
import json
import numpy as np


class NpEncoder(json.JSONEncoder):
    """处理 numpy 类型的 JSON 序列化"""
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super(NpEncoder, self).default(obj)


def analyze_csv_pro(file_path):
    """
    Refactored Analysis Engine: General + Financial Enhanced Mode.
    Follows Weighted Ratio rules and outputs structured data.
    """
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(json.dumps({"error": f"Read error: {str(e)}"}))
        return

    result = {
        "summary": {"rows": int(df.shape[0]), "cols": int(df.shape[1])},
        "insights": [],
        "data": {}
    }

    # --- 1. Domain Detection ---
    financial_keywords = ['revenue', 'profit', 'margin', 'cost', 'expense', 'income']
    is_financial = any(any(kw in col.lower() for kw in financial_keywords) for col in df.columns)
    result["summary"]["is_financial_data"] = is_financial

    # --- 2. Advanced Analysis ---
    
    # Example: Profitability Analysis (Weighted Ratios)
    if is_financial:
        # Find Revenue and Profit columns
        rev_col = next((c for c in df.columns if 'revenue' in c.lower() or 'sales' in c.lower()), None)
        profit_col = next((c for c in df.columns if 'gross_profit' in c.lower() or 'profit' in c.lower()), None)
        
        if rev_col and profit_col:
            total_rev = df[rev_col].sum()
            total_profit = df[profit_col].sum()
            weighted_margin = (total_profit / total_rev) * 100 if total_rev != 0 else 0
            
            result["insights"].append({
                "type": "financial_ratio",
                "metric": "Weighted Gross Margin",
                "value": round(weighted_margin, 2),
                "description": f"Total {profit_col} divided by Total {rev_col}. More accurate than simple average."
            })
        else:
            result["insights"].append({
                "type": "health_check",
                "status": "warning",
                "message": "Financial data detected but missing standard 'Revenue' or 'Profit' columns for weighted analysis."
            })

    # Example: Periodicity & Trend (Grouping by Year/Month)
    month_col = next((c for c in df.columns if 'month' in c.lower()), None)
    year_col = next((c for c in df.columns if 'year' in c.lower()), None)
    rev_col = next((c for c in df.columns if 'revenue' in c.lower() or 'sales' in c.lower()), None)
    
    if month_col and year_col and is_financial and rev_col:
        month_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        df['_sort'] = df[month_col].apply(lambda x: month_order.index(x) if x in month_order else 99)
        trend_df = df.sort_values([year_col, '_sort'])
        
        # Aggregate by period to avoid duplicates (e.g. 3 product lines per month)
        periodic_rev = trend_df.groupby([year_col, month_col, '_sort'])[rev_col].sum().reset_index().sort_values([year_col, '_sort'])
        
        labels = [f"{row[month_col]} {int(row[year_col])}" for _, row in periodic_rev.iterrows()]
        values = periodic_rev[rev_col].tolist()
        
        # 输出纯数据结构（不含图表配置）
        result["data"]["revenue_trend"] = {
            "labels": labels,
            "values": values
        }

    # Example: Margins by Category (Weighted)
    cat_col = next((c for c in df.columns if 'product' in c.lower() or 'category' in c.lower()), None)
    profit_col = next((c for c in df.columns if 'gross_profit' in c.lower() or 'profit' in c.lower()), None)
    
    if cat_col and is_financial and rev_col and profit_col:
        grouped = df.groupby(cat_col).agg({rev_col: 'sum', profit_col: 'sum'})
        grouped['margin'] = (grouped[profit_col] / grouped[rev_col] * 100).round(2)
        
        # 输出纯数据结构
        result["data"]["margin_by_category"] = {
            "categories": grouped.index.tolist(),
            "margins": grouped['margin'].tolist()
        }

    # Example: Revenue Composition
    if cat_col and rev_col:
        composition = df.groupby(cat_col)[rev_col].sum()
        
        # 输出纯数据结构
        result["data"]["revenue_composition"] = {
            name: float(value) for name, value in composition.items()
        }

    # --- 3. JSON Output ---
    print(json.dumps(result, cls=NpEncoder, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # 本脚本主要作为参考实现供 Agent 学习分析模式，
    # 也可直接执行进行快速概览：python analyze.py <csv_path>
    import sys
    if len(sys.argv) > 1:
        analyze_csv_pro(sys.argv[1])
    else:
        print(json.dumps({"error": "Usage: python analyze.py <csv_file_path>"}))
