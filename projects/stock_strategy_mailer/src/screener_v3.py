from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from .screener_v2 import StockScreenerV2, Candidate


class StockScreenerV3(StockScreenerV2):
    """优化版 V3：最近 6 个交易日涨停池明确不包含当日涨停。"""

    def get_completed_reference_date(self, target_date: date | None = None) -> date:
        """
        返回“当前交易日之前已经完成的最近一个交易日”。

        设计意图：
        - 无论是在盘中还是收盘后手动运行，
          “最近 6 个交易日涨停池”都不包含当天新增涨停；
        - 与用户策略口径保持一致：只使用当天之前已经完成的交易日。
        """
        target_date = target_date or self.get_cn_now().date()
        return self.get_previous_trade_date(target_date)

    def run_detailed(self) -> dict[str, Any]:
        start_ts = time.time()
        today = self.get_cn_now().date()
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
                    "analysis_end_date": "",
                    "limit_up_reference_excludes_today": True,
                },
            }

        completed_end_date = self.get_completed_reference_date(today)
        rt_universe = self.get_realtime_universe()
        recent_limit_up_codes = self.get_recent_limit_up_codes(completed_end_date)

        if recent_limit_up_codes:
            scan_df = rt_universe[rt_universe["代码"].isin(recent_limit_up_codes)].copy()
            mode = "recent_limit_up_pool_excluding_today"
        else:
            scan_df = rt_universe.sort_values("成交额", ascending=False).head(400).copy()
            mode = "turnover_top400_fallback"

        all_candidates: list[Candidate] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._evaluate_one, row, completed_end_date) for _, row in scan_df.iterrows()]
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
                "analysis_end_date": completed_end_date.strftime("%Y-%m-%d"),
                "limit_up_reference_excludes_today": True,
            },
        }
