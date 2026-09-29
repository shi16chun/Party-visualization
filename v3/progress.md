# v3 修订进度记录

每完成一张任务卡追加一条：卡号、日期、输出文件、关键参数、未解决问题。阶段签收另起一行记录。

| 卡号 | 完成日期 | 输出文件 | 未解决问题 |
| --- | --- | --- | --- |
| P0 准备 | 2026-09-29 | v3/REVISION_PLAN.md；v3/progress.md；v3/manuscript_v1_submitted.md；v3/manuscript_v1_media/；v3/v1_fix_checklist.md | 见下方P0条目 |
| A0 | 2026-09-29 | v3/data/accounts.csv；v3/data/audit/a0_probe.csv；v3/data/audit/a0_evidence.md；v3/data/raw/accounts/；v3/scripts/a0_probe_accounts.py；v3/scripts/a0_build_accounts.py | 见下方A0条目 |
| A1 |  |  |  |

## P0 准备（2026-09-29）

- 输出
  - `v3/REVISION_PLAN.md`：修订工作大纲原文，未改动。
  - `v3/manuscript_v1_submitted.md`、`v3/manuscript_v1_media/`：投稿版旧稿（docx，2026.08.28投稿），用pandoc 3.9转为markdown，正文未改，只加了标题层级与图片路径。
  - `v3/v1_fix_checklist.md`：第八节十项必须删改内容逐条定位到旧稿行号，附核对证据与处理卡号。
  - `v3/` 下按大纲目录约定建立子目录；`.gitignore` 排除 `v3/data/media/` 与Python缓存。
- 关键发现
  - 仓库根目录的 `manuscript.md` 是早于投稿版的草稿，标题、摘要、关键词与投稿版不同。大纲E卡写的输入“旧稿manuscript.md”，建议改为 `v3/manuscript_v1_submitted.md`，`manuscript.md` 中的参考文献表与英文摘要可作参考。
  - 旧数据实际抓取时间为2026-08-24 15:48–15:53 UTC，旧稿正文与图1注中的“8月4日”有误。
  - 除图2外，图1与回归表（第二个表4）在正文中也没有引用。
  - RNC第一人称命中15条中，按标题初判只有6条是RNC自身口吻。
  - 363条中10条超过60秒，均发布于2024年10月16日之后。
- 环境
  - 网络：YouTube、TikTok、X、huggingface.co、api.crossref.org 可访问；web.archive.org 仍被环境网络策略拦截（A5、A6依赖）；truthsocial.com 由网站返回403（A4时再试公开接口）。
  - 计算：4核CPU、无GPU、可用磁盘约30GB，容器为临时环境。
- 未解决问题
  - web.archive.org 需加入环境网络允许列表。
  - 仓库仍为公开状态。
  - 第十节决策点中TikTok与X数据接口两项，须在A2、A3开工前确定。

## A0 账号核验（2026-09-29）

- 输出
  - `v3/data/accounts.csv`：6个节点×4个平台共24行，无空值。除大纲要求的9列外，另有 role、status、handle_2024、active_in_window、window_evidence、followers_now、display_name_now、notes。
  - `v3/data/audit/a0_probe.csv`、`v3/data/raw/accounts/`：逐次探测的解析结果与原始返回。
  - `v3/data/audit/a0_evidence.md`：与大纲不一致之处、窗口期发布证据、采集问题、待决事项。
- 关键参数：请求间隔2秒；X用 api.fxtwitter.com 未登录接口；TikTok读用户主页与视频页内嵌数据；YouTube读频道 /about 页。
- 主要发现
  - 选举后改名的账号：Kamala HQ（X现名@HQNewsNow，TikTok现名@headquarters，YouTube现名@Headquarters）；RNC的X账号（2024年@GOP，现名@Republicans）。现@kamalahq、@GOP、@headquarters_67、@thedemocrats均为无关账号。
  - 大纲账号表的更正：DNC的TikTok为@democrats；RNC窗口期内无可核实的官方TikTok（@Republicans于2026年2月开设）；Kamala HQ在Truth Social有账号（原@BidenHQ）；Team Trump的YouTube频道窗口期无发布。
- 未解决问题
  - RNC的X账号、RNC与Team Trump的Truth Social账号，窗口期是否发布尚未取得帖子级证据，留待A3、A4。
  - Truth Social四个账号的ID与创建日期未取得（Cloudflare拦截）。
  - YouTube在本环境被限流（429与机器人验证），7条视频级探测失败，已记入a0_probe.csv。
  - 待你决定：a0_evidence.md第五节四项。
