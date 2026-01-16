import pandas as pd
import json
import numpy as np

def analyze_csv_pro(file_path):
    """
    Refactored Analysis Engine: General + Financial Enhanced Mode.
    Follows Weighted Ratio rules and strict ECharts formatting.
    """
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(json.dumps({"error": f"Read error: {str(e)}"}))
        return

    result = {
        "summary": {"rows": int(df.shape[0]), "cols": int(df.shape[1])},
        "insights": [],
        "charts": []
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
    
    if month_col and year_col and is_financial:
        month_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        df['_sort'] = df[month_col].apply(lambda x: month_order.index(x) if x in month_order else 99)
        trend_df = df.sort_values([year_col, '_sort'])
        
        # Aggregate by period to avoid duplicates (e.g. 3 product lines per month)
        periodic_rev = trend_df.groupby([year_col, month_col, '_sort'])[rev_col].sum().reset_index().sort_values([year_col, '_sort'])
        
        labels = [f"{row[month_col]} {int(row[year_col])}" for _, row in periodic_rev.iterrows()]
        
        result["charts"].append({
            "type": "line",
            "title": "Consolidated Revenue Trend",
            "xAxis": {"categories": labels, "label": "Period"},
            "yAxis": {"label": "Total Revenue"},
            "series": [{"name": "Revenue", "data": periodic_rev[rev_col].tolist()}]
        })

    # Example: Multi-Series Bar (Margins by Category)
    cat_col = next((c for c in df.columns if 'product' in c.lower() or 'category' in c.lower()), None)
    if cat_col and is_financial and rev_col and profit_col:
        grouped = df.groupby(cat_col).agg({rev_col: 'sum', profit_col: 'sum'})
        grouped['margin'] = (grouped[profit_col] / grouped[rev_col] * 100).round(2)
        
        result["charts"].append({
            "type": "bar",
            "title": "Weighted Margin by Category (%)",
            "xAxis": {"categories": grouped.index.tolist(), "label": cat_col},
            "yAxis": {"label": "Margin %"},
            "series": [{"name": "Weighted Margin", "data": grouped['margin'].tolist()}]
        })

    # Example: Pie Chart (Composition)
    if cat_col and rev_col:
        composition = df.groupby(cat_col)[rev_col].sum()
        result["charts"].append({
            "type": "pie",
            "title": f"{rev_col} Share by {cat_col}",
            "series": [{
                "name": "Revenue Share",
                "data": [{"name": k, "value": v} for k, v in composition.items()]
            }]
        })

    # --- 3. JSON Output ---
    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer): return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            return super(NpEncoder, self).default(obj)

    print("ANALYSIS_RESULT_START")
    print(json.dumps(result, cls=NpEncoder, ensure_ascii=False, indent=2))
    print("ANALYSIS_RESULT_END")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        analyze_csv_pro(sys.argv[1])
