#!/usr/bin/env python3
"""
投顾数学计算工具包 (Financial Advisor Math Toolkit)

支持两种使用方式：
1. CLI 模式：直接命令行执行，返回 JSON 结果
2. 模块模式：在 Python 中 import 使用

CLI 示例：
  python finance_formulas.py --type aip --pmt 3000 --rate 0.08 --periods 120
  python finance_formulas.py --type cagr --pv 100000 --fv 150000 --years 3
  python finance_formulas.py --type mdd --nav "1.0,1.1,0.95,1.2,0.8"
  python finance_formulas.py --type pmt --target 2000000 --rate 0.06 --periods 240
  python finance_formulas.py --type lump --pv 100000 --rate 0.08 --periods 12
  python finance_formulas.py --type years --pv 300000 --target 1000000 --rate 0.08
"""

import argparse
import json
import sys
import numpy as np

# ============================================================================
# 核心计算函数
# ============================================================================

def calc_aip_fv(pmt, annual_rate, periods, frequency='monthly'):
    """
    计算定期定额投资（定投）的终值 (Future Value)
    
    :param pmt: 每期投资金额
    :param annual_rate: 年化收益率 (如 0.06 表示 6%)
    :param periods: 总期数
    :param frequency: 频率 ('monthly', 'weekly', 'yearly')
    :return: 终值
    """
    if frequency == 'monthly':
        rate = annual_rate / 12
    elif frequency == 'weekly':
        rate = annual_rate / 52
    else:
        rate = annual_rate
        
    if rate == 0:
        return pmt * periods
        
    # 期末定投公式: FV = PMT * [((1 + r)^n - 1) / r]
    fv = pmt * ((pow(1 + rate, periods) - 1) / rate)
    return fv


def calc_lump_sum_fv(pv, annual_rate, periods, frequency='monthly'):
    """
    计算一次性投资的终值 (Future Value)
    
    :param pv: 初始投资金额
    :param annual_rate: 年化收益率
    :param periods: 总期数
    :param frequency: 频率 ('monthly', 'weekly', 'yearly')
    :return: 终值
    """
    if frequency == 'monthly':
        rate = annual_rate / 12
    elif frequency == 'weekly':
        rate = annual_rate / 52
    else:
        rate = annual_rate
    
    fv = pv * pow(1 + rate, periods)
    return fv


def calc_cagr(pv, fv, years):
    """
    计算复合年化收益率 (Compound Annual Growth Rate)
    
    :param pv: 现值 (初始投资)
    :param fv: 终值 (最终资产)
    :param years: 投资年限
    :return: CAGR
    """
    if pv <= 0 or years <= 0:
        return 0
    return pow(fv / pv, 1 / years) - 1


def calc_sharpe_ratio(returns, risk_free_rate=0.02):
    """
    计算夏普比率 (Sharpe Ratio)
    
    :param returns: 收益率序列 (list 或 np.array)
    :param risk_free_rate: 无风险收益率 (默认 2%)
    :return: 夏普比率
    """
    returns = np.array(returns)
    avg_return = np.mean(returns)
    std_return = np.std(returns)
    if std_return == 0:
        return 0
    return (avg_return - risk_free_rate) / std_return


def calc_max_drawdown(nav_list):
    """
    计算最大回撤 (Maximum Drawdown)
    
    :param nav_list: 净值序列 (list 或 np.array)
    :return: 最大回撤 (正数，如 0.20 表示 20% 回撤)
    """
    nav_list = np.array(nav_list)
    if len(nav_list) < 2:
        return 0
    
    cum_max = np.maximum.accumulate(nav_list)
    drawdowns = (cum_max - nav_list) / cum_max
    return float(np.max(drawdowns))


def calc_pmt_for_target(target_fv, annual_rate, periods, frequency='monthly'):
    """
    计算为了达到目标金额，每期需要投入的金额
    
    :param target_fv: 目标金额
    :param annual_rate: 年化收益率
    :param periods: 总期数
    :param frequency: 频率
    :return: 每期应投金额
    """
    if frequency == 'monthly':
        rate = annual_rate / 12
    elif frequency == 'weekly':
        rate = annual_rate / 52
    else:
        rate = annual_rate
        
    if rate == 0:
        return target_fv / periods
        
    pmt = target_fv * rate / (pow(1 + rate, periods) - 1)
    return pmt


def calc_years_to_target(pv, target_fv, annual_rate):
    """
    计算从初始投资到目标金额所需的年数
    
    :param pv: 初始投资
    :param target_fv: 目标金额
    :param annual_rate: 年化收益率
    :return: 所需年数
    """
    if annual_rate <= 0:
        return float('inf')
    if pv <= 0 or target_fv <= pv:
        return 0
    
    # 公式: FV = PV * (1 + r)^n
    # 推导: n = log(FV/PV) / log(1 + r)
    years = np.log(target_fv / pv) / np.log(1 + annual_rate)
    return years


def calc_irr(cash_flows):
    """
    计算内部收益率 (Internal Rate of Return)
    使用牛顿迭代法，避免依赖 numpy_financial
    
    :param cash_flows: 现金流序列，负数表示流出，正数表示流入
                       例如：[-10000, -10000, ..., 115000] 表示每月投入1万，最后拿到11.5万
    :return: 月度 IRR
    """
    cash_flows = np.array(cash_flows)
    
    # 牛顿迭代法求 IRR
    rate = 0.1  # 初始猜测
    for _ in range(100):
        # NPV 和 NPV 的导数
        npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cash_flows))
        npv_prime = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cash_flows))
        
        if abs(npv_prime) < 1e-10:
            break
            
        new_rate = rate - npv / npv_prime
        
        if abs(new_rate - rate) < 1e-10:
            rate = new_rate
            break
        rate = new_rate
    
    return rate


# ============================================================================
# CLI 入口
# ============================================================================

def format_result(calc_type, result, params):
    """
    格式化计算结果为 JSON
    """
    output = {
        "type": calc_type,
        "params": params,
        "result": result,
        "risk_tip": "测算结果仅供参考，不代表未来实际收益。投资有风险，入市需谨慎。"
    }
    return output


def main():
    parser = argparse.ArgumentParser(
        description='投顾数学计算工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  定投终值:   python finance_formulas.py --type aip --pmt 3000 --rate 0.08 --periods 120
  年化收益:   python finance_formulas.py --type cagr --pv 100000 --fv 150000 --years 3
  最大回撤:   python finance_formulas.py --type mdd --nav "1.0,1.1,0.95,1.2,0.8"
  目标反推:   python finance_formulas.py --type pmt --target 2000000 --rate 0.06 --periods 240
  一次性投资: python finance_formulas.py --type lump --pv 100000 --rate 0.08 --periods 12
  年限反推:   python finance_formulas.py --type years --pv 300000 --target 1000000 --rate 0.08
  内部收益率: python finance_formulas.py --type irr --cashflows "-10000,-10000,-10000,35000"
        """
    )
    
    parser.add_argument('--type', required=True, 
                        choices=['aip', 'cagr', 'mdd', 'sharpe', 'pmt', 'lump', 'irr', 'years'],
                        help='计算类型')
    parser.add_argument('--pmt', type=float, help='每期投资金额')
    parser.add_argument('--pv', type=float, help='现值/初始投资')
    parser.add_argument('--fv', type=float, help='终值')
    parser.add_argument('--target', type=float, help='目标金额')
    parser.add_argument('--rate', type=float, help='年化收益率 (如 0.08 表示 8%%)')
    parser.add_argument('--periods', type=int, help='总期数')
    parser.add_argument('--years', type=float, help='年数')
    parser.add_argument('--nav', type=str, help='净值序列，逗号分隔')
    parser.add_argument('--returns', type=str, help='收益率序列，逗号分隔')
    parser.add_argument('--cashflows', type=str, help='现金流序列，逗号分隔（负数为流出，正数为流入）')
    parser.add_argument('--rf', type=float, default=0.02, help='无风险利率 (默认 0.02)')
    parser.add_argument('--freq', type=str, default='monthly', 
                        choices=['monthly', 'weekly', 'yearly'],
                        help='频率 (默认 monthly)')
    
    args = parser.parse_args()
    
    try:
        if args.type == 'aip':
            # 定投终值
            if not all([args.pmt, args.rate is not None, args.periods]):
                print(json.dumps({"error": "定投计算需要 --pmt, --rate, --periods 参数"}))
                sys.exit(1)
            
            result_value = calc_aip_fv(args.pmt, args.rate, args.periods, args.freq)
            total_invested = args.pmt * args.periods
            profit = result_value - total_invested
            
            result = {
                "final_value": round(result_value, 2),
                "total_invested": round(total_invested, 2),
                "profit": round(profit, 2),
                "return_rate": f"{(profit / total_invested) * 100:.2f}%"
            }
            params = {"pmt": args.pmt, "rate": args.rate, "periods": args.periods, "freq": args.freq}
            
        elif args.type == 'lump':
            # 一次性投资终值
            if not all([args.pv, args.rate is not None, args.periods]):
                print(json.dumps({"error": "一次性投资计算需要 --pv, --rate, --periods 参数"}))
                sys.exit(1)
            
            result_value = calc_lump_sum_fv(args.pv, args.rate, args.periods, args.freq)
            profit = result_value - args.pv
            
            result = {
                "final_value": round(result_value, 2),
                "initial_investment": round(args.pv, 2),
                "profit": round(profit, 2),
                "return_rate": f"{(profit / args.pv) * 100:.2f}%"
            }
            params = {"pv": args.pv, "rate": args.rate, "periods": args.periods, "freq": args.freq}
            
        elif args.type == 'cagr':
            # 年化收益率
            if not all([args.pv, args.fv, args.years]):
                print(json.dumps({"error": "CAGR 计算需要 --pv, --fv, --years 参数"}))
                sys.exit(1)
            
            cagr = calc_cagr(args.pv, args.fv, args.years)
            result = {
                "cagr": round(cagr, 6),
                "cagr_percent": f"{cagr * 100:.2f}%"
            }
            params = {"pv": args.pv, "fv": args.fv, "years": args.years}
            
        elif args.type == 'mdd':
            # 最大回撤
            if not args.nav:
                print(json.dumps({"error": "最大回撤计算需要 --nav 参数"}))
                sys.exit(1)
            
            nav_list = [float(x.strip()) for x in args.nav.split(',')]
            mdd = calc_max_drawdown(nav_list)
            result = {
                "max_drawdown": round(mdd, 6),
                "max_drawdown_percent": f"{mdd * 100:.2f}%"
            }
            params = {"nav": nav_list}
            
        elif args.type == 'sharpe':
            # 夏普比率
            if not args.returns:
                print(json.dumps({"error": "夏普比率计算需要 --returns 参数"}))
                sys.exit(1)
            
            returns = [float(x.strip()) for x in args.returns.split(',')]
            sharpe = calc_sharpe_ratio(returns, args.rf)
            result = {
                "sharpe_ratio": round(sharpe, 4)
            }
            params = {"returns": returns, "risk_free_rate": args.rf}
            
        elif args.type == 'pmt':
            # 目标反推每期投入
            if not all([args.target, args.rate is not None, args.periods]):
                print(json.dumps({"error": "目标反推需要 --target, --rate, --periods 参数"}))
                sys.exit(1)
            
            pmt = calc_pmt_for_target(args.target, args.rate, args.periods, args.freq)
            total_invested = pmt * args.periods
            
            result = {
                "required_pmt": round(pmt, 2),
                "total_investment": round(total_invested, 2),
                "target": args.target
            }
            params = {"target": args.target, "rate": args.rate, "periods": args.periods, "freq": args.freq}
        
        elif args.type == 'years':
            # 反推年限：从初始投资到目标金额需要多少年
            if not all([args.pv, args.target, args.rate is not None]):
                print(json.dumps({"error": "年限反推需要 --pv, --target, --rate 参数"}))
                sys.exit(1)
            
            years = calc_years_to_target(args.pv, args.target, args.rate)
            growth_multiple = args.target / args.pv
            
            result = {
                "years_needed": round(years, 2),
                "initial_investment": args.pv,
                "target": args.target,
                "growth_multiple": f"{growth_multiple:.2f}x",
                "rate_percent": f"{args.rate * 100:.2f}%"
            }
            params = {"pv": args.pv, "target": args.target, "rate": args.rate}
        
        elif args.type == 'irr':
            # 内部收益率
            if not args.cashflows:
                print(json.dumps({"error": "IRR 计算需要 --cashflows 参数（现金流序列，逗号分隔）"}))
                sys.exit(1)
            
            cash_flows = [float(x.strip()) for x in args.cashflows.split(',')]
            irr = calc_irr(cash_flows)
            annual_irr = (1 + irr) ** 12 - 1  # 月度 IRR 转年化
            
            result = {
                "monthly_irr": round(irr, 6),
                "monthly_irr_percent": f"{irr * 100:.4f}%",
                "annual_irr": round(annual_irr, 6),
                "annual_irr_percent": f"{annual_irr * 100:.2f}%"
            }
            params = {"cash_flows": cash_flows}
            
        else:
            print(json.dumps({"error": f"未知的计算类型: {args.type}"}))
            sys.exit(1)
        
        output = format_result(args.type, result, params)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
