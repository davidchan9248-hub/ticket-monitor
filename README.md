# ⚽ Premier League 球票监控

监控 Arsenal、Chelsea、Man Utd、Spurs、Man City、Newcastle 球票，每个工作日通过 Telegram 自动推送。

## 架构

```
GitHub Actions (cron: 0 9 * * 1-5)
         │
         ▼
  monitor.py (ticket-monitor/src/monitor.py)
         │
    ┌────┴────┐
    ▼         ▼
票务平台      Telegram Bot
(StubHub/     │
Ticombo/      │
LiveFootball/  │
Fanpass)──────┘
```

## 监控球队

| 俱乐部 | 关键字 |
|:---|:---|
| 阿森纳 | arsenal, gunners |
| 切尔西 | chelsea, blues |
| 曼联 | manchester united, man utd, manu |
| 热刺 | tottenham, spurs |
| 曼城 | manchester city, man city |
| 纽卡斯尔 | newcastle, magpies |

## 部署步骤

### 1. Fork / Clone 本仓库

```bash
git clone https://github.com/YOUR_USERNAME/ticket-monitor.git
cd ticket-monitor
```

### 2. 配置 GitHub Secrets

进入 `Settings → Secrets and variables → Actions`，添加：

| Secret | 值 |
|:---|:---|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（@BotFather 获取） |
| `TELEGRAM_CHAT_ID` | 你的 Chat ID（@userinfobot 获取） |

### 3. 配置票务平台 API（可选）

各平台的 API Key 建议也存入 Secrets：

| Secret | 平台 |
|:---|:---|
| `STUBHUB_API_KEY` | StubHub API |
| `TICOMBO_API_KEY` | Ticombo API |

> 目前使用演示数据，正式上线需接入真实票务 API。

### 4. 验证 GitHub Actions

1. 进入仓库 `Actions` 页面
2. 点击 `Daily Ticket Monitor`
3. 点击 `Run workflow` → `Run workflow` 手动触发测试

### 5. 修改执行时间（如需要）

编辑 `.github/workflows/daily-ticket-check.yml` 中的 cron：

```yaml
schedule:
  # 工作日 9:00 UTC = 17:00 SGT
  - cron: '0 9 * * 1-5'
```

## 本地运行

```bash
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"

python src/monitor.py
```

## 目录结构

```
ticket-monitor/
├── .github/
│   └── workflows/
│       └── daily-ticket-check.yml   # GitHub Actions
├── src/
│   └── monitor.py                    # 主监控脚本
├── data/                             # 历史记录（gitignore）
├── requirements.txt
└── README.md
```

## 票务平台说明

| 平台 | 状态 | 备注 |
|:---|:---|:---|
| StubHub | 🔶 需API Key | 全球最大二手票平台，API需申请 |
| Ticombo | 🔶 需API Key | 欧洲热门，JS渲染需Selenium/Playwright |
| LiveFootball | 🔶 需爬虫 | 英国本地平台，反爬较严 |
| Fanpass | 🔶 需爬虫 | 大洋洲为主 |

> ⚠️ 各平台均有 Cloudflare 或反爬机制，建议申请官方 API 获取稳定数据源。

## 低价票判断逻辑

```python
status = "low_price"  # 原价70%以下
status = "hot"        # 高需求比赛
status = "in_stock"   # 正常有票
```

## 常见问题

**Q: 为什么显示演示数据？**
A: 真实票务 API 均需商业申请，当前为演示模式展示格式。接入真实 API 后替换 `demo_results()` 即可。

**Q: 如何添加更多球队？**
A: 在 `src/monitor.py` 的 `CLUBS` 字典中添加即可。

**Q: GitHub Actions 触发时间不对？**
A: cron 用 UTC 时间。`0 9 * * 1-5` = 每周一至五 9:00 UTC = 17:00 SGT。
