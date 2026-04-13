from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from .emailer import send_email
from .report_v2 import build_html_report_v2, build_text_report_v2
from .screener_v2 import StockScreenerV2


def get_cn_now_str() -> str:
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A股五日线回踩策略邮件推送（优化版）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印结果，不发送邮件")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    min_score = int(os.getenv("MIN_SCORE", "75"))
    max_candidates = int(os.getenv("MAX_CANDIDATES", "10"))
    screener = StockScreenerV2(min_score=min_score, max_candidates=max_candidates)

    detailed = screener.run_detailed()
    run_date = get_cn_now_str()

    html_body = build_html_report_v2(
        run_date=run_date,
        selected_rows=detailed["selected"],
        near_miss_rows=detailed["near_miss"],
        min_score=min_score,
        stats=detailed["stats"],
    )
    text_body = build_text_report_v2(
        run_date=run_date,
        selected_rows=detailed["selected"],
        near_miss_rows=detailed["near_miss"],
        min_score=min_score,
        stats=detailed["stats"],
    )

    subject = f"【A股策略选股-优化版】{run_date[:10]} 五日线回踩候选结果"

    if args.dry_run:
        print(text_body)
        return

    required_envs = ["EMAIL_TO", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"]
    missing = [key for key in required_envs if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"缺少必要环境变量: {', '.join(missing)}")

    send_email(subject=subject, html_body=html_body, text_body=text_body)
    print(
        f"邮件已发送，时间: {run_date}，正式候选数量: {len(detailed['selected'])}，接近阈值数量: {len(detailed['near_miss'])}，"
        f"分析数量: {detailed['stats'].get('scanned_count', 0)}，耗时: {detailed['stats'].get('elapsed_seconds', 0)} 秒"
    )


if __name__ == "__main__":
    main()
