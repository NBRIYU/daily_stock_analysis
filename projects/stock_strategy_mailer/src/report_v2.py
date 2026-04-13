from __future__ import annotations

from typing import Iterable


def _build_table(rows: list[dict]) -> str:
    if not rows:
        return "<p>无数据。</p>"
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
    return f"""
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


def build_html_report_v2(
    run_date: str,
    selected_rows: Iterable[dict],
    near_miss_rows: Iterable[dict],
    min_score: int,
    stats: dict,
) -> str:
    selected_rows = list(selected_rows)
    near_miss_rows = list(near_miss_rows)

    stats_html = f"""
    <ul>
      <li>最低分数阈值：{min_score}</li>
      <li>全市场初筛数量：{stats.get('universe_count', 0)}</li>
      <li>近6日涨停池数量：{stats.get('recent_limit_up_pool_count', 0)}</li>
      <li>实际分析数量：{stats.get('scanned_count', 0)}</li>
      <li>运行模式：{stats.get('mode', 'unknown')}</li>
      <li>运行耗时：{stats.get('elapsed_seconds', 0):.1f} 秒</li>
    </ul>
    """

    selected_html = _build_table(selected_rows) if selected_rows else "<p>今日没有达到正式阈值的候选股票。</p>"
    near_miss_section = ""
    if near_miss_rows:
        near_miss_section = f"""
        <h3>接近阈值的观察名单</h3>
        <p>以下股票未达到正式入选分数，但已接近你的阈值，可用于盘后复核。</p>
        {_build_table(near_miss_rows)}
        """

    return f"""
    <html>
      <body style=\"font-family: Arial, Helvetica, sans-serif; line-height: 1.5;\">
        <h2>A股五日线回踩策略选股结果（优化版）</h2>
        <p><strong>运行日期：</strong>{run_date}</p>
        <p>说明：本报告基于主板非 ST 股票、近 6 日涨停、趋势向上、五日线支撑等规则自动筛选，仅作策略执行参考，不构成投资建议。</p>
        {stats_html}
        <h3>正式入选名单</h3>
        {selected_html}
        {near_miss_section}
      </body>
    </html>
    """.strip()


def build_text_report_v2(
    run_date: str,
    selected_rows: Iterable[dict],
    near_miss_rows: Iterable[dict],
    min_score: int,
    stats: dict,
) -> str:
    selected_rows = list(selected_rows)
    near_miss_rows = list(near_miss_rows)

    lines = [
        "A股五日线回踩策略选股结果（优化版）",
        f"运行日期: {run_date}",
        f"最低分数阈值: {min_score}",
        f"全市场初筛数量: {stats.get('universe_count', 0)}",
        f"近6日涨停池数量: {stats.get('recent_limit_up_pool_count', 0)}",
        f"实际分析数量: {stats.get('scanned_count', 0)}",
        f"运行模式: {stats.get('mode', 'unknown')}",
        f"运行耗时: {stats.get('elapsed_seconds', 0):.1f} 秒",
        "",
        "正式入选名单:",
    ]

    if selected_rows:
        for idx, row in enumerate(selected_rows, start=1):
            lines.extend(
                [
                    f"{idx}. {row['code']} {row['name']} | 分数={row['score']} | 现价={row['latest_price']:.2f} | MA5={row['ma5']:.2f} | 距MA5={row['distance_to_ma5_pct']:.2f}% | 最近涨停日={row['last_limit_up_date']}",
                    f"   原因: {row['reason']}",
                ]
            )
    else:
        lines.append("今日没有达到正式阈值的候选股票。")

    if near_miss_rows:
        lines.extend(["", "接近阈值的观察名单:"])
        for idx, row in enumerate(near_miss_rows, start=1):
            lines.extend(
                [
                    f"{idx}. {row['code']} {row['name']} | 分数={row['score']} | 现价={row['latest_price']:.2f} | MA5={row['ma5']:.2f} | 距MA5={row['distance_to_ma5_pct']:.2f}% | 最近涨停日={row['last_limit_up_date']}",
                    f"   原因: {row['reason']}",
                ]
            )

    return "\n".join(lines)
