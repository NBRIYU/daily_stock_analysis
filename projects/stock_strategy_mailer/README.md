# A股强势主板股五日线回踩选股邮件项目

本项目基于你定义的交易策略，自动在**交易日北京时间上午 10:00** 左右执行选股，并将符合条件的股票清单发送到指定邮箱。

> 策略主题：从过去六个交易日内有涨停的沪深主板非 ST 股票中，筛选出价格靠近五日线、五日线具备支撑、整体趋势向上、形态相对良好的股票。

## 功能特性

- 自动筛选 **沪深主板非 ST 股票**
- 识别 **过去 6 个交易日内出现过涨停** 的标的
- 判断 **5 日线附近回踩 + 强支撑 + 趋势向上**
- 以分数制输出候选股票
- GitHub Actions 定时运行
- 通过 SMTP 自动发送结果到邮箱
- 支持本地手动运行和 GitHub 手动触发

## 当前策略量化实现

项目将原始交易思路量化为如下规则：

### 1. 股票池
- 仅保留沪深主板股票
- 排除 ST、*ST、退市整理、北交所、科创板、创业板
- 要求流动性正常

### 2. 最近 6 个交易日内有涨停
- 使用近 6 个已完成交易日的日线数据
- 非 ST 主板股票以 `涨跌幅 >= 9.7%` 近似判定涨停

### 3. 趋势向上
- `MA5` 向上
- `MA10` 向上
- 昨收盘位于 `MA20` 之上
- 近 10 个交易日价格结构保持相对上行

### 4. 五日线附近
- 当前价格距离昨日 `MA5` 不超过 `2.5%`
- 或盘中最低价回踩到 `MA5` 附近

### 5. 五日线强支撑
- 当前价站在 `MA5` 附近或上方
- 盘中最低价未明显跌穿 `MA5`
- 未破坏最近关键低点

### 6. 形态过滤
- 避免最近 3 个交易日连续大涨形成明显加速末端
- 避免长上影明显的弱收盘形态

> 说明：
> - 这是对策略的**程序化近似实现**，主要完成客观条件筛选。
> - “板块强度”“市场情绪”这类更主观的维度，当前版本未纳入强约束，可在后续版本继续扩展。

## 项目结构

```text
projects/stock_strategy_mailer/
├─ src/
│  ├─ __init__.py
│  ├─ screener.py
│  ├─ emailer.py
│  └─ main.py
├─ .env.example
├─ .gitignore
├─ requirements.txt
└─ README.md
```

工作流文件位于仓库根目录：

```text
.github/workflows/stock-strategy-mailer.yml
```

## 环境变量配置

将下面变量配置为 GitHub Secrets，或在本地写入 `.env` 文件：

| 变量名 | 说明 |
|---|---|
| `EMAIL_TO` | 收件人邮箱 |
| `SMTP_HOST` | SMTP 服务器地址 |
| `SMTP_PORT` | SMTP 端口 |
| `SMTP_USER` | SMTP 用户名 |
| `SMTP_PASS` | SMTP 密码 / 授权码 |
| `SMTP_FROM` | 发件邮箱，缺省时使用 `SMTP_USER` |
| `SMTP_USE_SSL` | 是否使用 SSL，默认 `true` |
| `MIN_SCORE` | 最低入选分数，默认 `75` |
| `MAX_CANDIDATES` | 邮件中最多展示的股票数量，默认 `20` |

### 共享仓库中的 GitHub Secrets 命名

由于这是放在 `daily_stock_analysis` 仓库中的独立子项目，工作流默认读取以下 Secrets：

- `STOCK_MAILER_EMAIL_TO`
- `STOCK_MAILER_SMTP_HOST`
- `STOCK_MAILER_SMTP_PORT`
- `STOCK_MAILER_SMTP_USER`
- `STOCK_MAILER_SMTP_PASS`
- `STOCK_MAILER_SMTP_FROM`
- `STOCK_MAILER_SMTP_USE_SSL`
- `STOCK_MAILER_MIN_SCORE`
- `STOCK_MAILER_MAX_CANDIDATES`

### 示例 `.env`

```env
EMAIL_TO=your_email@example.com
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your_sender@example.com
SMTP_PASS=your_authorization_code
SMTP_FROM=your_sender@example.com
SMTP_USE_SSL=true
MIN_SCORE=75
MAX_CANDIDATES=20
```

## 本地运行

### 1. 安装依赖

```bash
cd projects/stock_strategy_mailer
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 然后编辑 .env
```

### 3. 运行

```bash
python -m src.main
```

### 4. 仅打印，不发邮件

```bash
python -m src.main --dry-run
```

## GitHub Actions 配置方法

在仓库 `Settings -> Secrets and variables -> Actions` 中新增以下 Secrets：

- `STOCK_MAILER_EMAIL_TO`
- `STOCK_MAILER_SMTP_HOST`
- `STOCK_MAILER_SMTP_PORT`
- `STOCK_MAILER_SMTP_USER`
- `STOCK_MAILER_SMTP_PASS`
- `STOCK_MAILER_SMTP_FROM`
- `STOCK_MAILER_SMTP_USE_SSL`
- `STOCK_MAILER_MIN_SCORE`
- `STOCK_MAILER_MAX_CANDIDATES`

工作流已配置为：
- 每周一至周五 UTC `02:00` 执行，约等于北京时间 `10:00`
- 运行时会先检查是否为中国 A 股交易日，若不是交易日则自动退出且不发送空邮件

## 注意事项

1. GitHub Actions 的 `cron` 调度通常可满足日常使用，但不保证秒级绝对准时。
2. 行情数据依赖 AkShare 免费接口，若上游接口变更，需要同步调整代码。
3. 若你希望加入“板块热度”“涨停质量更细粒度判断”“卖点提醒”等模块，可以继续扩展。
4. 邮件发送成功依赖邮箱服务商允许 SMTP 登录，部分邮箱需要开启授权码。

## 后续可扩展方向

- 增加板块热度 / 题材强度评分
- 增加回撤幅度与量能结构约束
- 增加买入后跟踪和卖点提醒
- 输出 HTML 表格附件 / CSV
- 接入企业微信、Telegram、飞书机器人
