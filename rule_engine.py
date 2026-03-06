from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result(index: int, name: str, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "index": index,
        "rule_name": name,
        "status": "PASS" if passed else "FAIL",
        "reason": reason,
    }


def _not_available(index: int, name: str, reason: str) -> dict[str, Any]:
    """Return N/A status for metrics that cannot be evaluated."""
    return {
        "index": index,
        "rule_name": name,
        "status": "N/A",
        "reason": reason,
    }


def _manual_fail(index: int, name: str, reason: str) -> dict[str, Any]:
    """Mark as N/A for manual checks that require external context."""
    return _not_available(index, name, reason)


def evaluate_checklist(snapshot: dict[str, Any]) -> dict[str, Any]:
    company_name = snapshot.get("company_name", "Unknown")

    roce = _as_float(snapshot.get("roce"))
    debt_to_equity = _as_float(snapshot.get("debt_to_equity"))
    pe_ratio = _as_float(snapshot.get("pe_ratio"))
    peg_ratio = _as_float(snapshot.get("peg_ratio"))
    opm = _as_float(snapshot.get("operating_profit_margin"))
    sales_growth = _as_float(snapshot.get("sales_growth_3y"))
    profit_growth = _as_float(snapshot.get("profit_growth_3y"))
    dividend_yield = _as_float(snapshot.get("dividend_yield"))
    promoter_holding = _as_float(snapshot.get("promoter_holding"))
    promoter_pledge = _as_float(snapshot.get("promoter_pledge"))
    interest_coverage = _as_float(snapshot.get("interest_coverage"))
    roe = _as_float(snapshot.get("roe"))
    operating_cf_consistent = snapshot.get("operating_cf_consistent")
    opm_declining_3q = snapshot.get("opm_declining_3q")
    industry_text = str(snapshot.get("industry_text", "")).lower()

    is_banking = any(
        key in industry_text
        for key in ["bank", "finance", "financial services", "nbfc", "insurance"]
    )

    pegy = None
    if pe_ratio is not None and profit_growth is not None:
        denominator = profit_growth + (dividend_yield or 0)
        if denominator > 0:
            pegy = pe_ratio / denominator

    rules: list[dict[str, Any]] = []

    if roce is None:
        rules.append(_not_available(1, "ROCE > 15%", "ROCE data not available from Screener."))
    else:
        rules.append(
            _result(1, "ROCE > 15%", roce > 15, f"ROCE is {roce:.2f}%.")
        )

    if is_banking:
        rules.append(
            _result(
                2,
                "Debt to Equity < 0.5 (unless banking sector)",
                True,
                "Banking/financial profile detected, debt rule marked as exempt.",
            )
        )
    elif debt_to_equity is None:
        rules.append(
            _not_available(
                2,
                "Debt to Equity < 0.5 (unless banking sector)",
                "Debt to Equity value not found. May indicate minimal debt (common for IT companies).",
            )
        )
    else:
        rules.append(
            _result(
                2,
                "Debt to Equity < 0.5 (unless banking sector)",
                debt_to_equity < 0.5,
                f"Debt/Equity is {debt_to_equity:.2f}.",
            )
        )

    if operating_cf_consistent is None:
        rules.append(
            _not_available(
                3,
                "Operating cash flow consistent with net profit",
                "Could not derive cash flow vs net profit series from Screener annual tables.",
            )
        )
    else:
        rules.append(
            _result(
                3,
                "Operating cash flow consistent with net profit",
                bool(operating_cf_consistent),
                "Compared recent cash from operations with net profit trend.",
            )
        )

    if promoter_pledge is None:
        rules.append(
            _not_available(
                4,
                "Promoter pledge < 20%",
                "Promoter pledge value not available in free Screener data for this company.",
            )
        )
    else:
        rules.append(
            _result(4, "Promoter pledge < 20%", promoter_pledge < 20, f"Promoter pledge is {promoter_pledge:.2f}%.")
        )

    if pegy is None:
        rules.append(
            _not_available(5, "PEGY ratio < 1.5", "PEGY could not be computed due to missing growth/valuation inputs."))
    else:
        rules.append(_result(5, "PEGY ratio < 1.5", pegy < 1.5, f"Computed PEGY is {pegy:.2f}."))

    rules.append(
        _manual_fail(
            6,
            "Current PE below 5-year median",
            "5-year median PE is not directly available from public Screener HTML.",
        )
    )

    rules.append(
        _manual_fail(
            7,
            "Price at least 20% below DCF value",
            "DCF fair value is not consistently available without a custom valuation model.",
        )
    )

    rules.append(
        _manual_fail(
            8,
            "Sector exposure < 25% of portfolio",
            "Requires your portfolio allocation data.",
        )
    )

    rules.append(
        _manual_fail(
            9,
            "Stock outperforming Nifty over 6 months",
            "Needs benchmark return comparison data not scraped in this MVP.",
        )
    )

    rules.append(
        _manual_fail(
            10,
            "Price near support or 200-day EMA",
            "Needs historical price series and technical indicator calculation.",
        )
    )

    rules.append(
        _manual_fail(
            11,
            "Volume confirmation on entry",
            "Needs daily volume candle data and entry-date context.",
        )
    )

    rules.append(
        _manual_fail(
            12,
            "Investment thesis still valid",
            "Requires qualitative analyst judgement and latest business updates.",
        )
    )

    if opm_declining_3q is None:
        rules.append(
            _not_available(
                13,
                "Operating margin not declining for 3 consecutive quarters",
                "Quarterly OPM sequence could not be parsed reliably.",
            )
        )
    else:
        rules.append(
            _result(
                13,
                "Operating margin not declining for 3 consecutive quarters",
                not bool(opm_declining_3q),
                "Checked latest three OPM observations from available tables.",
            )
        )

    rules.append(
        _manual_fail(
            14,
            "No governance red flags",
            "Needs event-level checks (auditor changes, related-party transactions).",
        )
    )

    rules.append(
        _manual_fail(
            15,
            "Position size not exceeding 15% of portfolio",
            "Requires your current portfolio position sizing.",
        )
    )

    rules.append(
        _manual_fail(
            16,
            "Opportunity cost vs better PEGY alternative",
            "Needs ranking against your watchlist alternatives.",
        )
    )

    rules.append(
        _manual_fail(
            17,
            "Stock above 200-day moving average",
            "Needs historical price data and moving average computation.",
        )
    )

    rules.append(
        _manual_fail(
            18,
            "RSI not extremely overbought",
            "Needs technical RSI calculation from historical prices.",
        )
    )

    rules.append(
        _manual_fail(
            19,
            "Tax implications considered",
            "Requires investor-specific tax profile.",
        )
    )

    rules.append(
        _manual_fail(
            20,
            "Dividend timing checked",
            "Needs ex-dividend and purchase-date context.",
        )
    )

    rules.append(
        _manual_fail(
            21,
            "Trade documented for audit",
            "Requires manual confirmation from your trading journal.",
        )
    )

    if sales_growth is None or profit_growth is None:
        rules.append(
            _not_available(
                22,
                "Sales and profit growth healthy (3Y > 8%)",
                "Compounded growth data for both sales and profit was not found.",
            )
        )
    else:
        passed = sales_growth > 8 and profit_growth > 8
        rules.append(
            _result(
                22,
                "Sales and profit growth healthy (3Y > 8%)",
                passed,
                f"Sales growth 3Y: {sales_growth:.2f}%, Profit growth 3Y: {profit_growth:.2f}%.",
            )
        )

    rules.append(_manual_fail(23, "10-year survival test", "Requires long-horizon qualitative and cyclicality review."))

    rules.append(
        _manual_fail(
            24,
            "Simple understandable business model",
            "Requires qualitative understanding of business complexity.",
        )
    )

    if promoter_holding is None:
        rules.append(
            _not_available(
                25,
                "Founder/management ownership (skin in the game)",
                "Promoter holding data not found.",
            )
        )
    else:
        rules.append(
            _result(
                25,
                "Founder/management ownership (skin in the game)",
                promoter_holding >= 20,
                f"Promoter holding is {promoter_holding:.2f}%.",
            )
        )

    if interest_coverage is None:
        rules.append(
            _not_available(
                26,
                "Debt sustainability during high interest rates",
                "Interest coverage data unavailable.",
            )
        )
    else:
        rules.append(
            _result(
                26,
                "Debt sustainability during high interest rates",
                interest_coverage > 3,
                f"Interest coverage is {interest_coverage:.2f}.",
            )
        )

    rules.append(
        _manual_fail(
            27,
            "Portfolio diversification correlation check",
            "Requires correlation analysis against your holdings.",
        )
    )

    if roce is None:
        rules.append(_not_available(28, "ROIC above 15%", "ROIC proxy unavailable; ROCE data missing."))
    else:
        rules.append(_result(28, "ROIC above 15%", roce > 15, f"Using ROCE proxy: {roce:.2f}%."))

    if opm is None:
        rules.append(
            _not_available(
                29,
                "Pricing power (stable margins)",
                "Operating margin data not found.",
            )
        )
    else:
        rules.append(
            _result(
                29,
                "Pricing power (stable margins)",
                opm >= 15,
                f"Latest operating margin is {opm:.2f}%.",
            )
        )

    rules.append(
        _manual_fail(
            30,
            "Margin of safety (30% below intrinsic value)",
            "Needs intrinsic value model output.",
        )
    )

    rules.append(
        _manual_fail(
            31,
            "DCF and reverse-DCF valuation sanity check",
            "Needs DCF and reverse-DCF assumptions.",
        )
    )

    rules.append(
        _manual_fail(
            32,
            "Buying during pessimistic cycle sentiment",
            "Needs sentiment and cycle context beyond Screener ratios.",
        )
    )

    rules.append(
        _manual_fail(
            33,
            "Stage 2 technical uptrend",
            "Needs trend-structure analysis on historical price data.",
        )
    )

    if peg_ratio is None or profit_growth is None:
        rules.append(
            _not_available(
                34,
                "PEG ratio less than growth rate",
                "PEG ratio or growth rate missing.",
            )
        )
    else:
        rules.append(
            _result(
                34,
                "PEG ratio less than growth rate",
                peg_ratio < profit_growth,
                f"PEG ratio is {peg_ratio:.2f}, Profit growth (3Y) is {profit_growth:.2f}%.",
            )
        )

    passed_points = sum(1 for r in rules if r["status"] == "PASS")
    failed_points = sum(1 for r in rules if r["status"] == "FAIL")
    evaluated_points = passed_points + failed_points
    total_points = len(rules)
    score = round((passed_points / evaluated_points) * 100, 2) if evaluated_points else 0.0

    return {
        "stock_name": company_name,
        "passed_points": passed_points,
        "failed_points": failed_points,
        "evaluated_points": evaluated_points,
        "total_points": total_points,
        "score": score,
        "rules": rules,
        "key_metrics": {
            "roce": roce,
            "roe": roe,
            "debt_to_equity": debt_to_equity,
            "pe_ratio": pe_ratio,
            "peg_ratio": peg_ratio,
            "operating_profit_margin": opm,
            "sales_growth_3y": sales_growth,
            "profit_growth_3y": profit_growth,
            "dividend_yield": dividend_yield,
            "promoter_holding": promoter_holding,
            "promoter_pledge": promoter_pledge,
            "interest_coverage": interest_coverage,
        },
        "source_url": snapshot.get("ticker_url"),
    }
