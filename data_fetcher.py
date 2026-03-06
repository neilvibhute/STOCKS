from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SCREENER_BASE_URL = "https://www.screener.in"
SEARCH_API_PATH = "/api/company/search/"


@dataclass
class CompanySearchResult:
    company_id: int
    name: str
    url: str


class ScreenerClient:
    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def search_company(self, query: str) -> CompanySearchResult:
        params = {"q": query.strip()}
        response = self.session.get(
            urljoin(SCREENER_BASE_URL, SEARCH_API_PATH),
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json()

        if not results:
            raise ValueError(f"No company found for query: {query}")

        top = results[0]
        return CompanySearchResult(
            company_id=int(top["id"]),
            name=str(top["name"]),
            url=urljoin(SCREENER_BASE_URL, str(top["url"])),
        )

    def fetch_company_snapshot(self, query: str) -> dict[str, Any]:
        match = self.search_company(query)
        response = self.session.get(match.url, timeout=self.timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        print(f"[DEBUG] Fetched {len(response.text)} bytes from {match.url}")

        quick_ratios = self._parse_quick_ratios(soup)
        latest_rows = self._parse_latest_value_rows(soup)
        growth_tables = self._parse_compounded_growth_tables(soup)
        annual_rows = self._parse_annual_series_rows(soup)
        balance_sheet = self._parse_balance_sheet(soup)

        company_name = self._extract_company_name(soup) or match.name
        industry_text = self._extract_industry_text(soup)
        
        print(f"[DEBUG] Extracted {len(quick_ratios)} quick ratios")
        print(f"[DEBUG] Quick ratios: {list(quick_ratios.keys())}")

        # Try to compute debt-to-equity from balance sheet
        debt_to_equity = self._compute_debt_to_equity(balance_sheet)
        
        metrics: dict[str, Any] = {
            "company_name": company_name,
            "ticker_url": match.url,
            "industry_text": industry_text,
            "roce": self._first_numeric(quick_ratios, ["ROCE", "ROCE %"], latest_rows),
            "roe": self._first_numeric(quick_ratios, ["ROE", "ROE %"], latest_rows),
            "debt_to_equity": debt_to_equity,
            "pe_ratio": self._first_numeric(quick_ratios, ["Stock P/E", "P/E", "PE"], latest_rows),
            "peg_ratio": self._find_row_numeric(latest_rows, ["peg ratio", "peg"]),
            "operating_profit_margin": self._first_numeric(quick_ratios, ["OPM", "OPM %"], latest_rows),
            "sales_growth_3y": self._find_growth_value(growth_tables, "sales", "3 years"),
            "profit_growth_3y": self._find_growth_value(growth_tables, "profit", "3 years"),
            "dividend_yield": self._first_numeric(quick_ratios, ["Dividend Yield"], latest_rows),
            "promoter_holding": self._find_row_numeric(latest_rows, ["promoters", "promoter holding"]),
            "promoter_pledge": self._find_row_numeric(latest_rows, ["pledged percentage", "promoter pledge"]),
            "interest_coverage": self._find_row_numeric(latest_rows, ["interest coverage"]),
            "current_price": self._first_numeric(quick_ratios, ["Current Price"], latest_rows),
            "book_value": self._first_numeric(quick_ratios, ["Book Value"], latest_rows),
            "market_cap": self._first_numeric(quick_ratios, ["Market Cap"], latest_rows),
            "raw_growth_tables": growth_tables,
            "raw_quick_ratios": quick_ratios,
            "raw_latest_rows": latest_rows,
        }

        metrics["operating_cf_consistent"] = self._evaluate_operating_cf_consistency(annual_rows)
        metrics["opm_declining_3q"] = self._evaluate_opm_decline_3q(annual_rows)
        return metrics

    def _extract_company_name(self, soup: BeautifulSoup) -> str | None:
        title = soup.select_one("h1")
        if not title:
            return None
        text = title.get_text(" ", strip=True)
        return re.sub(r"\s+", " ", text)

    def _extract_industry_text(self, soup: BeautifulSoup) -> str:
        text_chunks = []
        for el in soup.select("div.company-info, section.about, div#top"):
            text = el.get_text(" ", strip=True)
            if text:
                text_chunks.append(text)
        return " ".join(text_chunks)[:2000]

    def _parse_quick_ratios(self, soup: BeautifulSoup) -> dict[str, float]:
        ratios: dict[str, float] = {}
        
        # First try the top-ratios section (more reliable)
        top_ratios_section = soup.find(id="top-ratios")
        if top_ratios_section:
            for item in top_ratios_section.select("li"):
                name_el = item.select_one("span.name")
                value_el = item.select_one("span.number, span.value")
                if not name_el or not value_el:
                    # Try alternate structure
                    text = item.get_text(" ", strip=True)
                    if not text or len(text) > 100:
                        continue
                    # Parse patterns like "Market Cap ₹ 5,32,594 Cr." or "ROCE 37.5 %"
                    parts = text.split()
                    if len(parts) >= 2:
                        # Extract numeric value from anywhere in the text
                        for part in parts:
                            num = self._to_float(part)
                            if num is not None:
                                label = text.split(part)[0].strip()
                                ratios[label] = num
                                break
                    continue
                
                name = re.sub(r"\s+", " ", name_el.get_text(" ", strip=True))
                value = self._to_float(value_el.get_text(" ", strip=True))
                if value is not None:
                    ratios[name] = value
        
        # Fallback: try general li.flex structure
        if not ratios:
            for item in soup.select("li.flex.flex-space-between"):
                name_el = item.select_one("span.name")
                value_el = item.select_one("span.value")
                if not name_el or not value_el:
                    continue
                name = re.sub(r"\s+", " ", name_el.get_text(" ", strip=True))
                value = self._to_float(value_el.get_text(" ", strip=True))
                if value is not None:
                    ratios[name] = value
        
        return ratios

    def _parse_latest_value_rows(self, soup: BeautifulSoup) -> dict[str, float]:
        rows: dict[str, float] = {}
        for tr in soup.select("table tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            label = re.sub(r"\s+", " ", cells[0].get_text(" ", strip=True)).strip().lower()
            if not label:
                continue

            values = []
            for cell in cells[1:]:
                num = self._to_float(cell.get_text(" ", strip=True))
                if num is not None:
                    values.append(num)
            if values:
                rows[label] = values[-1]
        return rows

    def _parse_compounded_growth_tables(self, soup: BeautifulSoup) -> dict[str, dict[str, float]]:
        parsed: dict[str, dict[str, float]] = {}
        for table in soup.select("table"):
            heading_el = table.select_one("th[colspan='2']")
            if not heading_el:
                continue

            heading = heading_el.get_text(" ", strip=True).lower()
            if "compounded sales growth" in heading:
                key = "sales"
            elif "compounded profit growth" in heading:
                key = "profit"
            else:
                continue

            values: dict[str, float] = {}
            for tr in table.select("tr"):
                tds = tr.find_all("td")
                if len(tds) != 2:
                    continue
                period = tds[0].get_text(" ", strip=True).lower().replace(":", "")
                num = self._to_float(tds[1].get_text(" ", strip=True))
                if period and num is not None:
                    values[period] = num
            if values:
                parsed[key] = values
        return parsed

    def _parse_annual_series_rows(self, soup: BeautifulSoup) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for tr in soup.select("table.data-table tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 3:
                continue

            row_name = cells[0].get_text(" ", strip=True).lower()
            if not row_name:
                continue

            series: list[float] = []
            for cell in cells[1:]:
                num = self._to_float(cell.get_text(" ", strip=True))
                if num is not None:
                    series.append(num)
            if len(series) >= 3:
                out[row_name] = series
        return out

    def _evaluate_operating_cf_consistency(self, annual_rows: dict[str, list[float]]) -> bool | None:
        cf = annual_rows.get("cash from operating activity +")
        net_profit = annual_rows.get("net profit +")
        if not cf or not net_profit:
            return None

        n = min(len(cf), len(net_profit), 5)
        cf_tail = cf[-n:]
        np_tail = net_profit[-n:]

        aligned = 0
        for cf_val, np_val in zip(cf_tail, np_tail):
            if np_val <= 0:
                continue
            if cf_val >= 0.8 * np_val:
                aligned += 1
        return aligned >= max(2, n - 1)

    def _evaluate_opm_decline_3q(self, annual_rows: dict[str, list[float]]) -> bool | None:
        opm = annual_rows.get("opm %")
        if not opm or len(opm) < 3:
            return None
        last3 = opm[-3:]
        return last3[0] > last3[1] > last3[2]

    def _find_growth_value(
        self, growth_tables: dict[str, dict[str, float]], section: str, period: str
    ) -> float | None:
        sec = growth_tables.get(section, {})
        period_norm = period.strip().lower()
        for key, value in sec.items():
            if period_norm in key:
                return value
        return None

    def _first_numeric(
        self,
        quick: dict[str, float],
        labels: list[str],
        latest_rows: dict[str, float],
    ) -> float | None:
        for label in labels:
            if label in quick:
                return quick[label]
        normalized = [x.lower() for x in labels]
        for row_label, value in latest_rows.items():
            for target in normalized:
                if target in row_label:
                    return value
        return None

    def _find_row_numeric(self, latest_rows: dict[str, float], keys: list[str]) -> float | None:
        keys = [k.lower() for k in keys]
        for row_label, value in latest_rows.items():
            if any(k in row_label for k in keys):
                return value
        return None

    def _parse_balance_sheet(self, soup: BeautifulSoup) -> dict[str, list[float]]:
        """Parse balance sheet section for debt and equity values."""
        out: dict[str, list[float]] = {}
        bs_section = soup.find(id="balance-sheet")
        if not bs_section:
            return out
        
        table = bs_section.find("table")
        if not table:
            return out
            
        for tr in table.select("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            
            row_name = cells[0].get_text(" ", strip=True).lower()
            if not row_name:
                continue
            
            series: list[float] = []
            for cell in cells[1:]:
                num = self._to_float(cell.get_text(" ", strip=True))
                if num is not None:
                    series.append(num)
            if series:
                out[row_name] = series
        
        return out
    
    def _compute_debt_to_equity(self, balance_sheet: dict[str, list[float]]) -> float | None:
        """Compute debt-to-equity ratio from balance sheet if available."""
        # Look for total debt and equity capital
        debt = None
        equity = None
        
        # Try to find debt
        for key in balance_sheet:
            if "borrowing" in key or "debt" in key:
                values = balance_sheet[key]
                if values:
                    debt = values[-1]  # Latest value
                    break
        
        # Try to find equity
        for key in balance_sheet:
            if "equity capital" in key or "shareholders fund" in key or "total equity" in key:
                values = balance_sheet[key]
                if values:
                    equity = values[-1]
                    break
        
        if debt is not None and equity is not None and equity > 0:
            return debt / equity
        
        return None
    
    @staticmethod
    def _to_float(raw_value: str) -> float | None:
        text = raw_value.replace(",", "").replace("\u20b9", "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None
