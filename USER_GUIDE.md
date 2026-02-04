# 远程监控与维护指南

既然你要出远门，这台 monitor bot 运行在 GitHub Actions 云端，**不受你本地电脑开关机影响**。你只需要在另一台电脑登录 GitHub 即可进行所有管理。

## 1. 紧急入口
建议你收藏以下链接，随时可以查看运行状态：
- **监控控制台 (Actions 页面)**: [https://github.com/lala1ala/monitor-bot/actions](https://github.com/lala1ala/monitor-bot/actions)
- **代码仓库**: [https://github.com/lala1ala/monitor-bot](https://github.com/lala1ala/monitor-bot)

## 2. 如果收到报错通知
我已经更新了代码 (`main.py`)，现在如果程序崩溃，会直接发送 **Telegram 报警** 给你。
收到报警后：
1. 打开上面的 [Actions 页面](https://github.com/lala1ala/monitor-bot/actions)。
2. 查看最近一次失败的 `Binance Monitor Task` 或 `Portfolio Monitor`。
3. 点击进去看 `Run Monitor Script` 的日志，了解原因（比如是 IP 限制、API 挂了还是其他）。

## 3. 如何手动重启
如果发现它挂了（GitHub 上显示红色的 ❌），或者你想立刻手动触发一次扫描：
1. 进入 [Actions 页面](https://github.com/lala1ala/monitor-bot/actions)。
2. 在左侧菜单点击 `Binance Monitor Task` (或者 `Portfolio Monitor`)。
3. 在右侧列表上方，会有一个蓝色的 **Run workflow** 按钮。
4. 点击它，再点绿色的 **Run workflow** 确认。
5. 等待几分钟，看是否变成绿色的 ✅。

## 4. 常见问题
- **Billing 额度**: 每个用于免费额度是 2000 分钟。目前设定是每小时运行一次（两个 bot 错开），理论上是够用的。如果月底发现额度不够（Actions 也就是停止运行），你可以考虑注册个新 GitHub 账号 fork 过去跑，或者等下个月自动恢复。
- **IP 限制**: 如果日志显示 `IP Restricted`，这是 GitHub 的云端 IP 被币安 ban 了。脚本里已经内置了代理池会自动重试，通常不需要你干预。如果连续报错，手动重启一次通常能换个新 IP。

祝你旅途愉快！放心，云端程序会自动跑的。
