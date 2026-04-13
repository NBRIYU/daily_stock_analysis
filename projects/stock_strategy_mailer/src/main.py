from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from .emailer import build_html_report, build_text_report, send_email
from .screener import StockScreener


def get_cn_now_str() -> str:
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A股五日线回踩策略邮件推送")
    parser.add_argument("--dry-run", action="store_true", help="仅打印结果，不发送邮件")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    min_score = int(os.getenv("MIN_SCORE", "75"))
    max_candidates = int(os.getenv("MAX_CANDIDATES", "20"))

    screener = StockScreener(min_score=min_score, max_candidates=max_candidates)
    if not screener.is_trade_day():
        print("今日非A股交易日，跳过选股和邮件发送。")
        return

    run_date = get_cn_now_str()
    rows = screener.run()

    html_body = build_html_report(run_date=run_date, rows=rows, min_score=min_score)
    text_body = build_text_report(run_date=run_date, rows=rows, min_score=min_score)

    subject = f"【A股策略选股】{run_date[:10]} 五日线回踩候选结果"

    if args.dry_run:
        print(text_body)
        return

    required_envs = ["EMAIL_TO", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"]
    missing = [key for key in required_envs if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"缺少必要环境变量: {', '.join(missing)}")

    send_email(subject=subject, html_body=html_body, text_body=text_body)
    print(f"邮件已发送，时间: {run_date}，候选数量: {len(rows)}")


if __name__ == "__main__":
    main()
