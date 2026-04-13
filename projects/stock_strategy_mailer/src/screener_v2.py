from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import akshare as ak
import numpy as np
import pandas as pd


MAINBOARD_PREFIXES = (
    "600",
    "601",
    "603",
    "605",
    "000",
    "001",
    "002",
    "003",
)

EXCLUDED_NAME_KEYWORDS = (
    "ST",
    "*ST",
    "退",
)


@dataclass
class Candidate:
    code: str
    name: str
    score: int
    latest_price: float
    ma5: float
    distance_to_ma5_pct: float
    last_limit_up_date: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "score": self.score,
            "latest_price": self.latest_price,
            "ma5": self.ma5,
            "distance_to_ma5_pct": self.distance_to_ma5_pct,
            "last_limit_up_date": self.last_limit_up_date,
            "reason": self.reason,
        }


class StockScreenerV2:
    def __init__(self, min_score: int = 75, max_candidates: int = 10, max_workers: int = 8) -> None:
        self.min_score = min_score
        self.max_candidates = max_candidates
        self.max_workers = max_workers
        self._trade_dates_cache: list[date] | None = None

    @staticmethod
    def get_cn_now() -> datetime:
        return datetime.utcnow() + timedelta(hours=8)

    def get_trade_dates(self) -> list[date]:
        if self._trade_dates_cache is None:
            trade_df = ak.tool_trade_date_hist_sina()
            trade_df["trade_date"] = pd.to_datetime(trade_df["trade_date"]).dt.date
            self._trade_dates_cache = trade_df["trade_date"].tolist()
        return self._trade_dates_cache

    def is_trade_day(self, target_date: date | None = None) -> bool:
        target_date = target_date or self.get_cn_now().date()
        return target_date in self.get_trade_dates()

    def get_previous_trade_date(self, target_date: date | None = None) -> date:
        target_date = target_date or self.get_cn_now().date()
        trade_dates = self.get_trade_dates()
        past_dates = [d for d in trade_dates if d < target_date]
        if not past_dates:
            raise ValueError("未找到上一个交易日")
        return past_dates[-1]

    def get_analysis_end_date(self, now: datetime | None = None) -> date:
        now = now or self.get_cn_now()
        today = now.date()
        if self.is_trade_day(today) and now.hour >= 15:
            return today
        return self.get_previous_trade_date(today)

    @staticmethod
    def _is_mainboard(code: str) -> bool:
        return code.startswith(MAINBOARD_PREFIXES)

    @staticmethod
    def _is_non_st(name: str) -> bool:
        upper_name = str(name).upper()
        return not any(keyword in upper_name for keyword in EXCLUDED_NAME_KEYWORDS)

    def get_realtime_universe(self) -> pd.DataFrame:
        df = ak.stock_zh_a_spot_em()
        df["代码"] = df["代码"].astype(str).str.zfill(6)
        df["名称"] = df["名称"].astype(str)
        df = df[df["代码"].map(self._is_mainboard)]
        df = df[df["名称"].map(self._is_non_st)]
        df = df[df["最新价"].notna()]
        df = df[df["成交额"].fillna(0) > 1.5e8]
        return df.copy()

    def _fetch_limit_up_pool_for_date(self, trade_date: date) -> set[str]:
        try:
            df = ak.stock_zt_pool_em(date=trade_date.strftime("%Y%m%d"))
            if df is None or df.empty:
                return set()
            code_col = "代码" if "代码" in df.columns else "股票代码" if "股票代码" in df.columns else None
            if code_col is None:
                return set()
            return set(df[code_col].astype(str).str.zfill(6).tolist())
        except Exception:
            return set()

    def get_recent_limit_up_codes(self, analysis_end_date: date) -> set[str]:
        trade_dates = [d for d in self.get_trade_dates() if d <= analysis_end_date]
        recent_dates = trade_dates[-6:]
        code_set: set[str] = set()
        for d in recent_dates:
            code_set |= self._fetch_limit_up_pool_for_date(d)
        return code_set

    @staticmethod
    def _prepare_hist_df(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["日期"] = pd.to_datetime(df["日期"])
        numeric_cols = ["开盘", "收盘", "最高", "最低", "成交量", "成交额", "涨跌幅"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["收盘", "最高", "最低"])
        df = df.sort_values("日期").reset_index(drop=True)
        df["MA5"] = df["收盘"].rolling(5).mean()
        df["MA10"] = df["收盘"].rolling(10).mean()
        df["MA20"] = df["收盘"].rolling(20).mean()
        return df

    def get_hist_data(self, code: str, end_date: date) -> pd.DataFrame:
        start_date = end_date - timedelta(days=90)
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="",
        )
        if df.empty:
            return df
        return self._prepare_hist_df(df)

    @staticmethod
    def _upper_shadow_ratio(row: pd.Series) -> float:
        body_top = max(row["开盘"], row["收盘"])
        full_range = max(row["最高"] - row["最低"], 1e-6)
        upper_shadow = max(row["最高"] - body_top, 0)
        return float(upper_shadow / full_range)

    @staticmethod
    def _has_recent_limit_up(hist: pd.DataFrame) -> tuple[bool, str]:
        recent = hist.tail(6)
        limit_rows = recent[recent["涨跌幅"] >= 9.7]
        if limit_rows.empty:
            return False, ""
        last_date = limit_rows.iloc[-1]["日期"].strftime("%Y-%m-%d")
        return True, last_date

    @staticmethod
    def _is_trend_up(hist: pd.DataFrame) -> bool:
        if len(hist) < 25:
            return False
        y = hist.iloc[-1]
        p1 = hist.iloc[-2]
        if pd.isna(y["MA5"]) or pd.isna(y["MA10"]) or pd.isna(y["MA20"]):
            return False
        if not (y["MA5"] > p1["MA5"] and y["MA10"] >= p1["MA10"] and y["收盘"] > y["MA20"]):
            return False
        recent10 = hist.tail(10)
        prev10 = hist.iloc[-20:-10]
        if prev10.empty:
            return False
        return bool(recent10["最高"].max() >= prev10["最高"].max() * 0.98 and recent10["最低"].min() >= prev10["最低"].min() * 0.97)

    @staticmethod
    def _not_acceleration_end(hist: pd.DataFrame) -> bool:
        recent3 = hist.tail(3)
        if len(recent3) < 3:
            return True
        big_rallies = (recent3["涨跌幅"] >= 5).sum()
        return bool(big_rallies <= 2)

    def _score_candidate(self, rt_row: pd.Series, hist: pd.DataFrame, last_limit_up_date: str) -> Candidate | None:
        if len(hist) < 25:
            return None

        y = hist.iloc[-1]
        p1 = hist.iloc[-2]
        latest_price = float(rt_row["最新价"])
        latest_low = float(rt_row.get("最低", np.nan)) if pd.notna(rt_row.get("最低", np.nan)) else latest_price
        latest_high = float(rt_row.get("最高", np.nan)) if pd.notna(rt_row.get("最高", np.nan)) else latest_price
        ma5 = float(y["MA5"])
        distance_pct = (latest_price - ma5) / ma5 * 100
        recent3_low = float(hist.tail(3)["最低"].min())
        intraday_range = max(latest_high - latest_low, 1e-6)
        intraday_upper_shadow = max(latest_high - latest_price, 0) / intraday_range

        if not self._is_trend_up(hist):
            return None
        if abs(distance_pct) > 6.0 and latest_low > ma5 * 1.02:
            return None
        if intraday_upper_shadow > 0.82 and latest_price < ma5 * 1.01:
            return None

        score = 20
        reasons: list[str] = ["近6个交易日内出现过涨停"]

        if y["MA5"] > p1["MA5"]:
            score += 8
        if y["MA10"] >= p1["MA10"]:
            score += 6
        if y["收盘"] > y["MA20"]:
            score += 6
        if self._is_trend_up(hist):
            score += 5
            reasons.append("MA5/MA10向上，整体趋势保持上行")

        if abs(distance_pct) <= 4.0 or latest_low <= ma5 * 1.02:
            score += 14
            reasons.append("现价回踩至MA5附近")
        elif abs(distance_pct) <= 5.5:
            score += 6

        if latest_price >= ma5 * 0.985 and latest_low >= ma5 * 0.955 and latest_low >= recent3_low * 0.97:
            score += 16
            reasons.append("回踩后仍保持较强支撑")
        elif latest_price >= ma5 * 0.97 and latest_low >= ma5 * 0.94:
            score += 8

        if self._not_acceleration_end(hist):
            score += 5
        if self._upper_shadow_ratio(y) <= 0.55 and intraday_upper_shadow <= 0.72:
            score += 5
            reasons.append("近期未见明显顶部破坏形态")
        if float(rt_row["成交额"]) > 5e8:
            score += 5

        return Candidate(
            code=str(rt_row["代码"]),
            name=str(rt_row["名称"]),
            score=int(score),
            latest_price=latest_price,
            ma5=ma5,
            distance_to_ma5_pct=round(distance_pct, 2),
            last_limit_up_date=last_limit_up_date,
            reason="；".join(reasons),
        )

    def _evaluate_one(self, row: pd.Series, analysis_end_date: date) -> Candidate | None:
        code = str(row["代码"])
        hist = self.get_hist_data(code, analysis_end_date)
        if hist.empty:
            return None
        has_limit_up, last_limit_up_date = self._has_recent_limit_up(hist)
        if not has_limit_up:
            return None
        return self._score_candidate(row, hist, last_limit_up_date)

    def run_detailed(self) -> dict[str, Any]:
        start_ts = time.time()
        now = self.get_cn_now()
        today = now.date()
        if not self.is_trade_day(today):
            return {
                "selected": [],
                "near_miss": [],
                "stats": {
                    "universe_count": 0,
                    "recent_limit_up_pool_count": 0,
                    "scanned_count": 0,
                    "mode": "non_trade_day",
                    "elapsed_seconds": 0.0,
                },
            }

        analysis_end_date = self.get_analysis_end_date(now)
        rt_universe = self.get_realtime_universe()
        recent_limit_up_codes = self.get_recent_limit_up_codes(analysis_end_date)

        if recent_limit_up_codes:
            scan_df = rt_universe[rt_universe["代码"].isin(recent_limit_up_codes)].copy()
            mode = "recent_limit_up_pool"
        else:
            scan_df = rt_universe.sort_values("成交额", ascending=False).head(400).copy()
            mode = "turnover_top400_fallback"

        all_candidates: list[Candidate] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._evaluate_one, row, analysis_end_date) for _, row in scan_df.iterrows()]
            for future in as_completed(futures):
                try:
                    candidate = future.result()
                except Exception:
                    candidate = None
                if candidate is not None:
                    all_candidates.append(candidate)

        all_candidates.sort(key=lambda x: (x.score, -abs(x.distance_to_ma5_pct), x.latest_price), reverse=True)
        selected = [item.to_dict() for item in all_candidates if item.score >= self.min_score][: self.max_candidates]
        near_miss_floor = max(self.min_score - 10, 65)
        near_miss = [item.to_dict() for item in all_candidates if near_miss_floor <= item.score < self.min_score][: self.max_candidates]

        elapsed = time.time() - start_ts
        return {
            "selected": selected,
            "near_miss": near_miss,
            "stats": {
                "universe_count": int(len(rt_universe)),
                "recent_limit_up_pool_count": int(len(recent_limit_up_codes)),
                "scanned_count": int(len(scan_df)),
                "mode": mode,
                "elapsed_seconds": round(elapsed, 1),
                "analysis_end_date": analysis_end_date.strftime("%Y-%m-%d"),
            },
        }
