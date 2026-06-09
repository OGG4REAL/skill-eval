#!/usr/bin/env python3
"""
月度交易统计脚本
用于分析银行交易数据的月度统计信息
"""

import pandas as pd
import json
import sys
import numpy as np
from datetime import datetime
from typing import Dict, List, Any


class NumpyEncoder(json.JSONEncoder):
    """处理 numpy 类型的 JSON 序列化"""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


# 交易类型分类定义
BUSINESS_TYPES = ['BUSINESS', 'NEFT', 'RTGS', 'IMPS', 'UPI', 'POS', 'CHEQUE', 'TRF_OUT', 'TRF_IN']
CASH_TYPES = ['CASH_DEPOSIT', 'CASH_WITHDRAWAL', 'ATM', 'CASH_PICKUP']


def load_data(filepath: str) -> pd.DataFrame:
    """加载银行交易数据"""
    df = pd.read_csv(filepath)

    # 转换日期字段
    df['DATE'] = pd.to_datetime(df['DATE'], format='%Y-%m-%d', errors='coerce')
    df['VALUE DATE'] = pd.to_datetime(df['VALUE DATE'], format='%Y-%m-%d', errors='coerce')

    return df


def filter_by_account(df: pd.DataFrame, account_no: str = None) -> pd.DataFrame:
    """按账户号过滤数据"""
    if account_no is None:
        account_no = df['Account No'].iloc[0]

    # 统一类型比较：尝试将 account_no 转为与 DataFrame 列一致的类型
    col_dtype = df['Account No'].dtype
    if pd.api.types.is_numeric_dtype(col_dtype):
        try:
            account_no = int(account_no)
        except (ValueError, TypeError):
            pass

    return df[df['Account No'] == account_no].copy()


def get_monthly_key(date: pd.Timestamp) -> str:
    """获取年月键值 (格式: YYYY-MM)"""
    return f"{date.year}-{date.month:02d}"


def calculate_business_stats(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    计算业务收支统计
    按月统计 TXN_TYPE 属于业务大类的交易
    """
    # 过滤业务类型交易
    business_df = df[df['TXN_TYPE'].isin(BUSINESS_TYPES)].copy()

    # 按月分组
    business_df['month_key'] = business_df['DATE'].apply(get_monthly_key)

    stats = {}
    for month_key, month_df in business_df.groupby('month_key'):
        # 业务收入
        income_mask = month_df['DEPOSIT AMT'].notna() & (month_df['DEPOSIT AMT'] > 0)
        income_count = income_mask.sum()
        income_total = month_df.loc[income_mask, 'DEPOSIT AMT'].sum()

        # 业务支出
        expense_mask = month_df['WITHDRAWAL AMT'].notna() & (month_df['WITHDRAWAL AMT'] > 0)
        expense_count = expense_mask.sum()
        expense_total = month_df.loc[expense_mask, 'WITHDRAWAL AMT'].sum()

        stats[month_key] = {
            'month': month_key,
            'business_income_count': int(income_count),
            'business_income_total': round(float(income_total), 2),
            'business_expense_count': int(expense_count),
            'business_expense_total': round(float(expense_total), 2)
        }

    # 按月份排序
    return [stats[k] for k in sorted(stats.keys())]


def calculate_gross_stats(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    计算总收支汇总
    按月统计所有交易（不过滤 TXN_TYPE）
    """
    df['month_key'] = df['DATE'].apply(get_monthly_key)

    stats = {}
    for month_key, month_df in df.groupby('month_key'):
        # 总收入
        income_mask = month_df['DEPOSIT AMT'].notna() & (month_df['DEPOSIT AMT'] > 0)
        income_count = income_mask.sum()
        income_total = month_df.loc[income_mask, 'DEPOSIT AMT'].sum()

        # 总支出
        expense_mask = month_df['WITHDRAWAL AMT'].notna() & (month_df['WITHDRAWAL AMT'] > 0)
        expense_count = expense_mask.sum()
        expense_total = month_df.loc[expense_mask, 'WITHDRAWAL AMT'].sum()

        # 月净现金流
        net_cash_flow = income_total - expense_total

        stats[month_key] = {
            'month': month_key,
            'total_income_count': int(income_count),
            'total_income_total': round(float(income_total), 2),
            'total_expense_count': int(expense_count),
            'total_expense_total': round(float(expense_total), 2),
            'net_cash_flow': round(float(net_cash_flow), 2)
        }

    # 按月份排序
    return [stats[k] for k in sorted(stats.keys())]


def calculate_cash_stats(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    计算现金流水分析
    按月统计 TXN_TYPE 属于现金大类的交易
    """
    # 过滤现金类型交易
    cash_df = df[df['TXN_TYPE'].isin(CASH_TYPES)].copy()

    # 按月分组
    cash_df['month_key'] = cash_df['DATE'].apply(get_monthly_key)

    # 获取每月总交易数（用于计算占比）
    df['month_key'] = df['DATE'].apply(get_monthly_key)
    monthly_total_counts = df.groupby('month_key').size().to_dict()

    stats = {}
    for month_key, month_df in cash_df.groupby('month_key'):
        # 现金存款
        deposit_mask = month_df['DEPOSIT AMT'].notna() & (month_df['DEPOSIT AMT'] > 0)
        deposit_count = deposit_mask.sum()
        deposit_total = month_df.loc[deposit_mask, 'DEPOSIT AMT'].sum()

        # 现金取款
        withdrawal_mask = month_df['WITHDRAWAL AMT'].notna() & (month_df['WITHDRAWAL AMT'] > 0)
        withdrawal_count = withdrawal_mask.sum()
        withdrawal_total = month_df.loc[withdrawal_mask, 'WITHDRAWAL AMT'].sum()

        # 现金交易占比
        cash_count = deposit_count + withdrawal_count
        total_count = monthly_total_counts.get(month_key, 0)
        cash_ratio = round((cash_count / total_count * 100), 2) if total_count > 0 else 0

        stats[month_key] = {
            'month': month_key,
            'cash_deposit_count': int(deposit_count),
            'cash_deposit_total': round(float(deposit_total), 2),
            'cash_withdrawal_count': int(withdrawal_count),
            'cash_withdrawal_total': round(float(withdrawal_total), 2),
            'cash_transaction_ratio': round(float(cash_ratio), 2)
        }

    # 按月份排序
    return [stats[k] for k in sorted(stats.keys())]


def main():
    """主函数"""
    # 默认输入文件路径
    input_file = 'sessions/bank_transactions_labeled.csv'
    account_no = None

    # 解析命令行参数
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        account_no = sys.argv[2]

    try:
        # 加载数据
        df = load_data(input_file)

        # 按账户过滤
        df = filter_by_account(df, account_no)

        # 计算三个维度的统计
        business_stats = calculate_business_stats(df)
        gross_stats = calculate_gross_stats(df)
        cash_stats = calculate_cash_stats(df)

        # 输出结果
        result = {
            'account_no': df['Account No'].iloc[0] if len(df) > 0 else account_no,
            'business_credits_debits': business_stats,
            'gross_transaction_totals': gross_stats,
            'cash_flow_analysis': cash_stats
        }

        print(json.dumps(result, ensure_ascii=False, indent=2, cls=NumpyEncoder))

    except FileNotFoundError:
        print(json.dumps({'error': f'File not found: {input_file}'}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()