# A3 X 采集可行性测试（2026-10-03）

## 一、免费路线：USC 2024大选X公开数据集

- 来源：Balasubramanian, Zou, Narayana, You, Luceri & Ferrara，A Public Dataset Tracking Social Media Discourse about the 2024 U.S. Presidential Election on Twitter/X（arXiv:2411.00376），https://github.com/sinking8/x-24-us-election ，CC BY-NC-SA 4.0。按关键词收集，覆盖2024-05-01至11-30，881个数据块，约4285万行。
- 处理：`v3/scripts/a3_usc24_filter.py` 逐块下载，按2024年账号名筛出本研究7个账号的帖子，并用user字段中的数字ID复核（7320行全部一致），数据块筛完即删。881块全部处理成功。筛出结果 `v3/data/raw/x/usc24_matches.csv.gz`，逐块日志 `v3/data/audit/x_usc24_chunks.csv`。
- 覆盖评估：`v3/scripts/a3_usc24_coverage.py`，结果 `v3/data/audit/x_usc24_coverage.csv`。

| 账号（2024年名） | 节点 | 窗口期去重条数 | 有帖子的天数（共108天） | 收集期内实际发帖数下限 | 覆盖率上限 |
| --- | --- | --- | --- | --- | --- |
| TheDemocrats | DNC | 205 | 48 | 2605 | 11.3% |
| GOP | RNC | 550 | 59 | 3419 | 16.7% |
| KamalaHQ | Kamala HQ | 290 | 72 | 1564 | 18.5% |
| KamalaHarris | Kamala Harris | 313 | 59 | 739 | 44.0% |
| TeamTrump | Team Trump | 48 | 26 | 2057 | 2.4% |
| TrumpWarRoom | Trump War Room | 637 | 65 | 6952 | 9.5% |
| realDonaldTrump | Donald J. Trump | 201 | 51 | 377 | 57.8% |

- “实际发帖数下限”取同一账号在数据集中最大与最小累计发帖数（statusesCount）之差。数据集未记录抓取时间，只能得出覆盖率上限，真实覆盖率更低。
- 7320行中有4818行是同一帖子被重复收录；按帖子ID去重后全部时段2506条，窗口期2244条。
- 收录的几乎全是原创与引用帖，回复极少，转发为0。关键词检索的方式决定了它只收录含选举关键词的帖子，Kamala HQ大量只有表情符号或短句配视频的帖子不会被收录。

结论：该数据集不能作为X发布量的全量来源，不能用于产量配置（D1）与节奏同步（D3）的测量。可作两种辅助用途：一是A3全量采集后的交叉核对；二是这些帖子在2024年抓取时记录的互动数，抓取时间未知但早于2026年，可作同期指标的补充，使用时说明这一限制。

## 二、其他路线

| 路线 | 能否取得2024年窗口期全量 | 说明 |
| --- | --- | --- |
| X官方接口，按账号取时间线 | 部分 | 该接口只返回账号最近约3200条帖子。按现有累计发帖数推算，特朗普与哈里斯2024年以来的发帖仍在3200条以内，可以取到；DNC、RNC、Kamala HQ、Trump War Room此后各发了数千至上万条，取不到窗口期 |
| X官方接口，全量历史检索 | 能 | 需要提供全量历史检索的接口档位，费用以X开发者平台当前公布为准 |
| 本地浏览器登录后按日检索（from:账号 since/until） | 能，较慢 | 免费，需一个X账号；7个账号×108天约756次检索，受频率限制，预计需本地运行一到数天；账号有被限制的风险 |
| 未登录第三方接口（A0所用） | 否 | 只能按帖子ID取单条，不能列时间线；可用于补全已知ID的帖子 |
