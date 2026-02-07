# 🛡️ BTC Decision System 部署指南

此脚本集成了 Fear & Greed 指数、年化资金费率以及 MA200/111 技术指标，并实现了基于成交量的“智能扫描”优化。

## GitHub Actions 自动运行设置

1.  **上传代码**：确保 `btc_monitor.py` 和 `.github/workflows/btc_daily_report.yml` 已提交到您的仓库。
2.  **配置密钥 (Secrets)**：
    *   在 GitHub 仓库中，点击 **Settings** -> **Secrets and variables** -> **Actions**。
    *   点击 **New repository secret**，添加以下三个变量：
        - `DISCORD_WEBHOOK_URL`: 您的 Discord 频道 Webhook 链接。
        - `COINALYZE_KEY`: 您的 Coinalyze API Key (在 Coinalyze.net 免费申请)。
        - `COINGLASS_SECRET`: (可选) 您的 Coinglass API Key (当前主要用于备选参考)。
3.  **启动**：
    *   脚本已配置为每天 **00:00** 和 **12:00 (UTC)** 自动运行。
    *   您也可以在 **Actions** 标签页手动点击 `BTC Decision System Daily Report` -> `Run workflow` 立即触发一次。

## 本地运行
如果在本地测试，请确保安装了依赖：
```bash
pip install requests
python btc_monitor.py
```
*注意：由于免费版 API 限制，脚本在获取全网持仓数据时可能会有短暂的 rate limit 等待，这是正常现象。*
