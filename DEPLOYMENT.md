# ☁️ 云端监控机器人部署指南 (GitHub Actions)

只需简单几步，即可将机器人部署到 GitHub，让它每 20 分钟自动为您工作。

## 第一步：准备代码

您已经有了自动生成的代码：
1.  `portfolio_bot/cloud_portfolio.py` (核心逻辑)
2.  `.github/workflows/portfolio.yml` (定时任务配置)

## 第二步：上传到 GitHub

1.  **登录 GitHub** 并创建一个新仓库（Repository）。
    *   起个名字，比如 `my-crypto-monitor`。
    *   **重要**：选择 **Private** (私有)，因为你要在这运行涉及资产的代码（虽然密钥是分开的，但私有更安全）。

2.  **推送代码** (在您的本地终端执行)：
    ```powershell
    # 1. 初始化 Git (如果还没做过)
    git init
    
    # 2. 添加文件
    git add .
    
    # 3. 提交
    git commit -m "Deploy portfolio bot"
    
    # 4. 关联远程仓库 (替换为您刚才创建的 GitHub 链接)
    git remote add origin https://github.com/您的用户名/my-crypto-monitor.git
    
    # 5. 推送
    git branch -M main
    git push -u origin main
    ```

## 第三步：配置密钥 (Secrets)

这是最关键的一步！我们需要把 API Key 告诉 GitHub，但不能直接写在代码里。

1.  打开您 GitHub 仓库的网页。
2.  点击上方的 **Settings** (设置)。
3.  在左侧栏找到 **Secrets and variables** -> 点击 **Actions**。
4.  点击绿色按钮 **New repository secret**。
5.  依次添加以下变量（名字必须完全一样，值填您的真实 Key）：

    | Name (变量名) | Secret (值) | 说明 |
    | :--- | :--- | :--- |
    | `TELEGRAM_BOT_TOKEN` | `123456:ABC-DEF...` | **必填** TG 机器人 Token |
    | `TELEGRAM_CHAT_ID` | `987654321` | **必填** 您的用户 ID |
    | `BINANCE_API_KEY` | `vmPU...` | 选填，查币安需要 |
    | `BINANCE_SECRET` | `Nhsq...` | 选填，查币安需要 |
    | `GATE_API_KEY` | `xxxx` | 选填，查 Gate 需要 |
    | `GATE_SECRET` | `xxxx` | 选填，查 Gate 需要 |
    | `HYPERLIQUID_WALLET` | `0x...` | 选填，查 HL 需要 |

## 第四步：启动与测试

1.  点击仓库上方的 **Actions** 标签页。
2.  在左侧点击 **Portfolio Monitor**。
3.  点击右侧的 **Run workflow** 按钮，再点绿色的 **Run workflow**。
4.  等待几秒钟，刷新页面，您应该会看到一个黄色或绿色的任务正在运行。
    *   ✅ **绿色**：运行成功！您的 Telegram 应该会收到一条报告。
    *   ❌ **红色**：运行失败。点击进去可以看到报错信息（通常是 Key 填错了）。

---

### 🕒 关于自动运行
从现在开始，每隔 **20分钟**，GitHub 会自动运行一次检查。
*   如果币价平稳，它什么都不做。
*   如果暴跌 (>2%)，它会报警。
*   每 4 小时，它会发一次周报。
