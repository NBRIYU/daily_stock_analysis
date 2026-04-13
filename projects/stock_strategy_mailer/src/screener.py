from __future__ import annotations

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
    "N",
    "C",
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


class StockScreener:
    def __init__(self, min_score: int = 75, max_candidates: int = 20) -> None:
        self.min_score = min_score
        self.max_candidates = max_candidates

    @staticmethod
    def get_cn_now() -> datetime:
        return datetime.utcnow() + timedelta(hours=8)

    @staticmethod
    def get_trade_dates() -> list[date]:
        trade_df = ak.tool_trade_date_hist_sina()
        trade_df["trade_date"] = pd.to_datetime(trade_df["trade_date"]).dt.date
        return trade_df["trade_date"].tolist()

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
        df = df[df["成交额"].fillna(0) > 2e8]
        return df.copy()

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
        start_date = end_date - timedelta(days=120)
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
        if not (y["MA5"] > p1["MA5"] and y["MA10"] > p1["MA10"] and y["收盘"] > y["MA20"]):
            return False
        recent10 = hist.tail(10)
        prev10 = hist.iloc[-20:-10]
        if prev10.empty:
            return False
        recent_high = recent10["最高"].max()
        prev_high = prev10["最高"].max()
        recent_low = recent10["最低"].min()
        prev_low = prev10["最低"].min()
        return bool(recent_high >= prev_high and recent_low >= prev_low * 0.98)

    @staticmethod
    def _not_acceleration_end(hist: pd.DataFrame) -> bool:
        recent3 = hist.tail(3)
        if len(recent3) < 3:
            return True
        big_rallies = (recent3["涨跌幅"] >= 5).sum()
        return bool(big_rallies < 3)

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

        score = 0
        reasons: list[str] = []

        score += 20
        reasons.append("近6个交易日内出现过涨停")

        if y["MA5"] > p1["MA5"]:
            score += 8
        if y["MA10"] > p1["MA10"]:
            score += 8
        if y["收盘"] > y["MA20"]:
            score += 4
        if self._is_trend_up(hist):
            score += 5
            reasons.append("MA5/MA10向上，整体趋势保持上行")
        else:
            return None

        near_ma5 = abs(distance_pct) <= 2.5 or latest_low <= ma5 * 1.01
        if near_ma5:
            score += 12
            reasons.append("现价处于MA5附近")
        else:
            return None

        key_low = float(hist.tail(3)["最低"].min())
        if latest_price >= ma5 * 0.995 and latest_low >= ma5 * 0.97 and latest_low >= key_low * 0.985:
            score += 20
            reasons.append("盘中回踩后仍保持对MA5的支撑")
        else:
            return None

        if self._not_acceleration_end(hist):
            score += 5
        if self._upper_shadow_ratio(y) <= 0.45:
            score += 5
            reasons.append("近期未出现明显加速末端或长上影破坏")

        if float(rt_row["成交额"]) > 5e8:
            score += 5

        intraday_range = max(latest_high - latest_low, 1e-6)
        intraday_upper_shadow = max(latest_high - latest_price, 0) / intraday_range
        if intraday_upper_shadow > 0.7 and latest_price < ma5 * 1.01:
            return None

        if score < self.min_score:
            return None

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

    def run(self) -> list[dict[str, Any]]:
        today = self.get_cn_now().date()
        if not self.is_trade_day(today):
            return []

        prev_trade_date = self.get_previous_trade_date(today)
        universe = self.get_realtime_universe()
        candidates: list[Candidate] = []

        for _, row in universe.iterrows():
            code = str(row["代码"])
            try:
                hist = self.get_hist_data(code, prev_trade_date)
                if hist.empty:
                    continue
                has_limit_up, last_limit_up_date = self._has_recent_limit_up(hist)
                if not has_limit_up:
                    continue
                candidate = self._score_candidate(row, hist, last_limit_up_date)
                if candidate is not None:
                    candidates.append(candidate)
            except Exception:
                continue

        candidates.sort(key=lambda x: (x.score, -abs(x.distance_to_ma5_pct), x.latest_price), reverse=True)
        return [item.to_dict() for item in candidates[: self.max_candidates]]
