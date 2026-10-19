# AI 投顾持仓看板

一个跑在云端的持仓监控：每个交易日收盘后自动拉净值、算盈亏、更新网页看板。
**电脑关机也不影响**——计算在 GitHub 的服务器上完成，你只需要打开一个链接。

---

## 它每天做什么

北京时间 **周一至周五 20:30**，GitHub Actions 自动执行：

1. 读 `holdings.csv` 里的份额与成本
2. 逐只拉取最新单位净值（雪球蛋卷公开接口，19 只全部覆盖）
3. 计算市值、累计盈亏、当日盈亏、A/B 两块占比
4. 写入 `docs/data.json`（含最近 250 个交易日的市值曲线）
5. 部署到 GitHub Pages

打开 `https://<你的用户名>.github.io/<仓库名>/` 就是最新看板。

---

## 目录结构

```
holdings.csv              持仓台账（改这里）
scripts/fetch.py          抓净值 + 计算，只用标准库
docs/index.html           看板页面，零外部依赖
docs/data.json            每天自动生成，不要手改
.github/workflows/daily.yml   定时任务定义
```

---

## 部署（三步）

### 1. 建仓库

登录 GitHub → 右上角 `+` → **New repository**

- 名称：`ai-advisor`（随意）
- 可见性：**Public**（Private 仓库要开 GitHub Pages 需要付费 Pro）
- **不要**勾选 Add README / .gitignore / license，建一个空仓库

### 2. 推代码

在本目录执行（把 `你的用户名` 换成实际的）：

```bash
git remote add origin https://github.com/你的用户名/ai-advisor.git
git branch -M main
git push -u origin main
```

第一次 push 会弹出浏览器让登录 GitHub，授权完即可。

### 3. 打开 Pages

仓库 → **Settings** → 左侧 **Pages** →
`Build and deployment` 的 Source 选 **GitHub Actions**（不要选 Deploy from a branch）。

保存后回到 **Actions** 标签页，点一次 `每日净值更新` → **Run workflow** 手动跑一遍，
几十秒后 `docs/` 就部署好了。之后每天 20:30 自动跑，不用再管。

---

## 改持仓

用 Excel 打开 `holdings.csv` 改，注意：

- 列顺序不要动：`代码,名称,份额,单位成本,分组`
- 代码保留前导零（`014080` 不能变成 `14080`）
- 分组只有 `A` 和 `B` 两种
- 保存为 **CSV UTF-8**（Excel 另存时选「CSV UTF-8 (逗号分隔)」）

改完在 GitHub 网页上打开 `holdings.csv` → 右上角铅笔图标 → 粘贴新内容 → Commit。
或者本地 `git commit && git push`。下一次运行自动生效。

**卖出/申购后的份额怎么填**：份额 = 原份额 ± 金额 ÷ 确认日净值。当场不知道确认净值时，
先按最新公布净值估算，第二天净值出来后修正一次即可。

---

## 已知口径

| 项目 | 说明 |
|---|---|
| 当日盈亏 | 用日增长率反推：`市值 − 市值/(1+日增长率%)`，比两位小数净值相减精确 |
| QDII 净值 | 006328（中证海外中国互联网）天然滞后一个交易日，页面会打「滞后1日」标记 |
| 节假日 | cron 只认周一到周五，A 股休市日会空跑一次。页面顶部会出现「本次运行没有取到新的净值」的提示，数字沿用上一交易日，不会算错 |
| 富国/中庚等 | 部分基金净值公布晚于 20:30，若某次没抓到会用上一次的缓存值并标注 |
| 动作延迟 | GitHub 的定时任务可能延迟几分钟到半小时，属正常 |

---

## 隐私提醒

`holdings.csv` 和 `docs/data.json` 都会存在仓库里，也就是说**你的份额、成本、市值对任何知道这个链接的人可见**。

如果 GitHub 仓库设为 Public，理论上可以被搜索引擎或爬虫发现。介意的话有两个办法：

1. **用一个小号 GitHub 账号**建这个仓库，不关联任何公开身份——这是最省事的做法
2. **让我改成私密模式**：把持仓放进 GitHub Secrets，历史数据不放仓库而是用 Actions 缓存。
   代价是每次改持仓要去仓库设置里更新 Secret，比直接改 CSV 麻烦

仓位金额本身是比较私人的信息，建议先按第 1 条处理。

---

## 本地调试

```bash
python scripts/fetch.py
cd docs && python -m http.server 8899
# 浏览器打开 http://127.0.0.1:8899
```

脚本只用 Python 标准库，不需要装任何依赖。
