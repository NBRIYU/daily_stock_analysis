from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable


def _get_bool_env(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def send_email(subject: str, html_body: str, text_body: str | None = None) -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)
    email_to = os.environ["EMAIL_TO"]
    use_ssl = _get_bool_env("SMTP_USE_SSL", True)

    recipients: list[str] = [item.strip() for item in email_to.split(",") if item.strip()]
    if not recipients:
        raise ValueError("EMAIL_TO 未配置有效收件人")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = ", ".join(recipients)

    if text_body:
        message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, recipients, message.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, recipients, message.as_string())


def build_html_report(run_date: str, rows: Iterable[dict], min_score: int) -> str:
    rows = list(rows)

    if rows:
        table_rows = "\n".join(
            f"""
            <tr>
              <td>{row['code']}</td>
              <td>{row['name']}</td>
              <td>{row['score']}</td>
              <td>{row['latest_price']:.2f}</td>
              <td>{row['ma5']:.2f}</td>
              <td>{row['distance_to_ma5_pct']:.2f}%</td>
              <td>{row['last_limit_up_date']}</td>
              <td>{row['reason']}</td>
            </tr>
            """.strip()
            for row in rows
        )
        table_html = f"""
        <table border=\"1\" cellspacing=\"0\" cellpadding=\"6\" style=\"border-collapse: collapse; font-size: 14px;\">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>评分</th>
              <th>现价</th>
              <th>MA5</th>
              <th>距MA5</th>
              <th>最近涨停日</th>
              <th>入选原因</th>
            </tr>
          </thead>
          <tbody>
            {table_rows}
          </tbody>
        </table>
        """
    else:
        table_html = "<p>今日未筛选出符合条件的股票。</p>"

    return f"""
    <html>
      <body style=\"font-family: Arial, Helvetica, sans-serif; line-height: 1.5;\">
        <h2>A股五日线回踩策略选股结果</h2>
        <p><strong>运行日期：</strong>{run_date}</p>
        <p><strong>最低分数阈值：</strong>{min_score}</p>
        <p>说明：本报告基于主板非 ST 股票、近 6 日涨停、趋势向上、五日线支撑等规则自动筛选，仅作策略执行参考，不构成投资建议。</p>
        {table_html}
      </body>
    </html>
    """.strip()


def build_text_report(run_date: str, rows: Iterable[dict], min_score: int) -> str:
    rows = list(rows)
    header = [
        "A股五日线回踩策略选股结果",
        f"运行日期: {run_date}",
        f"最低分数阈值: {min_score}",
        "",
    ]
    if not rows:
        return "\n".join(header + ["今日未筛选出符合条件的股票。"])

    lines: list[str] = header[:]
    for idx, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"{idx}. {row['code']} {row['name']} | 分数={row['score']} | 现价={row['latest_price']:.2f} | MA5={row['ma5']:.2f} | 距MA5={row['distance_to_ma5_pct']:.2f}% | 最近涨停日={row['last_limit_up_date']}",
                f"   原因: {row['reason']}",
            ]
        )
    return "\n".join(lines)
