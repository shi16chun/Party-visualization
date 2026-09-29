# A0 账号核验证据与说明

核验日期：2026-09-29。结果表：`v3/data/accounts.csv`。探测原始记录：`v3/data/audit/a0_probe.csv` 与 `v3/data/raw/accounts/`。

## 一、方法

1. `v3/scripts/a0_probe_accounts.py` 逐个探测账号主页：YouTube读频道 /about 页，TikTok读用户主页内嵌数据，X用未登录的第三方接口 api.fxtwitter.com，Truth Social用其Mastodon兼容接口。
2. 选举后改名的账号较多，只看handle会找错人。对每个节点再取一条到两条2024年的帖子或视频，查它现在归属的账号数字ID。帖子ID不随改名变化，现归属账号即2024年的发布账号。
3. 帖子ID来自检索结果与新闻、官网嵌入的链接，来源在下文逐条列出。
4. `v3/scripts/a0_build_accounts.py` 把核验判断与探测数字合成总表，数字字段一律取自探测表，不手填。

## 二、与大纲账号表不一致之处

| 节点 | 平台 | 大纲写法 | 核验结果 | 依据 |
| --- | --- | --- | --- | --- |
| DNC | TikTok | @thedemocrats（待核） | 官方账号为@democrats（ID 7044304201086321670，2021年注册）；现@thedemocrats为无关个人账号 | 2024-08-22代表大会视频 7406055642676464939 现归属@democrats；@democrats简介为 The official TikTok account of the Democratic Party |
| RNC | TikTok | @gop（待核） | 窗口期内无可核实的官方账号。RNC官方TikTok @Republicans于2026年2月开设；@gop注册于2024-09-24（ID编码），现无内容 | [The Hill](https://thehill.com/homenews/campaign/5726555-republican-party-tiktok-account/)、[Fox News](https://www.foxnews.com/politics/rnc-rolls-out-powerful-new-tiktok-strategy-to-win-over-key-demographic-after-trumps-2024-success) |
| RNC | X | @GOP | 2024年的@GOP（ID 11134252，2007年注册）现名@Republicans；现@GOP为2026-04-20新注册账号 | gop.com 2024-05-20页面嵌入的 twitter.com/GOP/status/1792584647336931731、1792600850860327031 现归属ID 11134252 |
| RNC | Truth Social | 待核 | 存在@RNC主页 | 检索结果 https://truthsocial.com/@RNC ；接口被拦截，未取得ID |
| Kamala HQ | YouTube | 待核是否有独立频道 | 有：@Headquarters（UCnniIiQ9zAOjTcnct0xccig），2024年1月起为Biden-Harris HQ内容，窗口期内有发布 | 视频 GsXS8WudinM（2024-10-26）、w_yGrsxNprA（2024-09-24）；页面未见认证标记，订阅1460 |
| Kamala HQ | TikTok | @kamalahq | 原账号现名@headquarters（ID 7334124418954200106，2024-02-10注册，即原@bidenhq）；现@kamalahq为2025年11月注册的无关账号 | 视频 7400033789335948575（2024-08-06）、7431356795391692074（2024-10-30）现归属该账号；[CNN 2026-02-05](https://www.cnn.com/2026/02/05/politics/kamala-hq-account-kamala-harris) |
| Kamala HQ | X | @KamalaHQ | 原账号现名@HQNewsNow（ID 3315264553，2015年注册）；2026年2月曾改名@headquarters_67，后再改；现@headquarters_67为无关账号 | 帖子 1815212766912803099（2024-07-22）、1834237601659703754（2024-09-12）现归属该账号；[The Hill](https://thehill.com/homenews/campaign/5724017-harris-campaign-accounts-restored/)、[Washington Examiner](https://www.washingtonexaminer.com/news/4448934/kamala-hq-account-changes-x-username-after-backlash-over-67/) |
| Kamala HQ | Truth Social | 无 | **存在**：@KamalaHQ，原@BidenHQ（2023年10月开设），2024年7月改名 | Truth Social官方账号2024-07-23发帖欢迎@KamalaHQ（[Newsweek](https://www.newsweek.com/kamala-harris-campaign-account-truth-social-1969556)、[Washington Examiner](https://www.washingtonexaminer.com/news/campaigns/presidential/3096248/truth-social-welcomes-harris-campaign/)） |
| Team Trump | YouTube | 待核 | @teamtrump频道存在，但最新视频为2016-11-06，窗口期无发布 | 视频 vST61W4bGm8（2016-11-06），频道共23条视频，均为2016年竞选内容 |
| Team Trump | Truth Social | 待核 | 存在@TeamTrump主页 | 检索结果 https://truthsocial.com/@TeamTrump |
| Donald J. Trump | YouTube | Donald J Trump | 频道名Donald J Trump，handle为@DonaldJTrumpforPresident | 频道 /about 页 |

## 三、窗口期发布证据

| 节点 | YouTube | TikTok | X | Truth Social |
| --- | --- | --- | --- | --- |
| DNC | 旧数据Shorts 11条（iyxa3eCv44U，2024-08-20） | 7406055642676464939（2024-08-22） | 1833680183540191305（2024-09-11） | 未发现官方账号 |
| RNC | 旧数据Shorts 163条（qGd4-MKK5_s，2024-07-24） | 未见 | 未取得窗口期帖子，待A3 | 未核实，待A4 |
| Kamala HQ | GsXS8WudinM（2024-10-26）、w_yGrsxNprA（2024-09-24） | 7400033789335948575（2024-08-06）、7431356795391692074（2024-10-30） | 1815212766912803099（2024-07-22）、1834237601659703754（2024-09-12） | 据报道选举期间每隔几天发帖，待A4 |
| Kamala Harris | 旧数据Shorts 156条（f6hcPwHIGc0，2024-07-23） | 7395695233276595487（2024-07-25）、7426486234593217838（2024-10-16） | 1851815659144872236（2024-10-31） | 未发现官方账号 |
| Team Trump | 无（最新视频2016-11-06） | 7433202628072394030（2024-11-03） | 1835314099757916355（2024-09-15） | 未核实，待A4 |
| Donald J. Trump | 旧数据Shorts 33条（-U3fvlYkQa4，2024-08-20） | 7403175874607975710（2024-08-15）、7427237451954965791（2024-10-18） | 1823035759655264697（2024-08-12，此前约一年未在X发帖，见[Variety](https://variety.com/2024/digital/news/donald-trump-returns-x-twitter-1236104163/)） | 个人发布主阵地，待A4 |

帖子ID的检索来源：X与TikTok帖子来自搜索引擎对 x.com、tiktok.com 帖子页的收录结果；RNC的两条X帖子来自 https://gop.com/commentary/palm-beach-playbook-may-20-2024/ 页面嵌入。

## 四、本次遇到的采集问题（影响后续任务卡）

| 平台 | 问题 | 影响 |
| --- | --- | --- |
| YouTube | 本环境多次请求后（频道页、列表与单条视频合计数十次），单条视频页返回429，yt-dlp提示需登录确认不是机器人；频道 /about 页此前正常 | A1需要限速、分批，或改在你本地运行；a0_probe.csv中7条YouTube视频探测记为失败，Kamala HQ与Team Trump频道的视频日期取自限流前的yt-dlp输出（未存原始返回，A1会重新取得） |
| TikTok | 用户主页可读；yt-dlp按账号列视频的接口返回空内容 | A2需另找列表路线（浏览器会话或研究接口） |
| X | 未登录的第三方接口可查用户资料与单条帖子，不能列时间线 | A3需浏览器自动化或付费接口 |
| Truth Social | 全部请求被Cloudflare拦截（含浏览器指纹伪装） | A4需在你本地运行，或使用第三方存档 |
| 互联网档案馆 | web.archive.org 被平台出口策略拦截 | A5、A6在你本地运行 |

## 五、需要你决定的事项

1. **Kamala HQ 的 YouTube 频道**：@Headquarters频道内容与改名链吻合，但页面未见认证标记、订阅只有1460。是否作为Kamala HQ的YouTube节点纳入？
2. **特朗普 YouTube 频道归属**：窗口期内特朗普一侧只有一个活跃的YouTube频道（Donald J Trump，handle为@DonaldJTrumpforPresident），Team Trump频道窗口期无发布。这个频道记为候选人个人节点还是竞选团队节点？
3. **共和党一侧的快速回应账号**：Kamala HQ自称竞选的快速回应账号（2024-07-22 UTC帖子 1815212766912803099：the official rapid response page of Vice President Harris’ presidential campaign）。特朗普一侧X上另有@TrumpWarRoom（ID 1108472017144201216，2019年注册，现简介为 The official War Room account of President Donald J. Trump's political operation），@TeamTrump则是竞选官方号。竞选团队节点是否加入@TrumpWarRoom，或改用它？@TrumpWarRoom在2024年的简介与运营方未核实。
4. **Kamala HQ 的 Truth Social 账号**：大纲原写无，核验后存在。A4是否纳入？
