# 本地运行指南

有些采集步骤在云端环境被平台拦截，需要在作者本地电脑运行，结果推回仓库分支 `claude/confident-thompson-apj01s`。本文件按任务卡逐项说明。

## 准备（只需一次）

1. 安装 Python 3.11 或更高版本。
2. 取得仓库最新代码（任选其一）：
   - 已装 git：`git clone https://github.com/shi16chun/Party-visualization.git`，进入文件夹后 `git checkout claude/confident-thompson-apj01s`；以后每次运行前 `git pull`。
   - 未装 git：在 GitHub 网页切换到分支 `claude/confident-thompson-apj01s`，点 Code → Download ZIP，解压。
3. 在仓库文件夹里打开命令行，安装依赖：
   ```
   pip install playwright curl_cffi tzdata
   python -m playwright install chromium
   ```

## A2 TikTok 视频清单

1. 在仓库文件夹里运行：
   ```
   python v3/scripts/a2_collect_tiktok.py list --profile-dir tiktok_profile
   ```
2. 脚本会依次打开5个账号（democrats、headquarters、kamalaharris、teamtrump、realdonaldtrump）的主页，模拟手机浏览并自动下滑，直到内容早于2024年7月21日。
3. 出现验证码时，在弹出的窗口里手动完成。若视频区显示“Something went wrong”，可在窗口里登录TikTok账号后重新运行，登录状态保存在 `tiktok_profile` 文件夹，下次沿用。
4. 每个账号结束时命令行会打印一行，例如 `kamalaharris items 300 in_window 250 pages=9 blocked_pages=0 ...`。blocked_pages大于0说明有被拦截的页，可对该账号单独重跑：`python v3/scripts/a2_collect_tiktok.py list --nodes kamalaharris --profile-dir tiktok_profile`。重跑会与已取得的结果合并，不会覆盖。
5. 运行结束后，把以下文件推回分支（git push，或在GitHub网页上传到 `v3/data/raw/tiktok/` 与 `v3/data/audit/`）：
   - `v3/data/raw/tiktok/*__list.jsonl`
   - `v3/data/raw/tiktok/*__list_log.jsonl`
   - `v3/data/audit/tiktok_pull_log.csv`
6. 不要上传 `tiktok_profile` 文件夹，里面有登录信息。

脚本只读取公开页面上的视频元数据，不采集评论与其他用户信息。
