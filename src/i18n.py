"""Bilingual UI strings for the static site — English (default) + Chinese.

EVERY visitor-facing string on the website lives here as an en/zh pair, side
by side, so the two language versions can never drift apart: templates contain
no hardcoded prose, and a missing translation raises at build time.

Rules (owner's decisions):
  * English is the DEFAULT language (site root); Chinese lives under /zh/.
  * Company names, manager names, quarter labels (2026-Q1), and financial
    terms/abbreviations (13F, AUM, ETF, CUSIP, SEC EDGAR) stay in English.
  * When adding or changing site copy, add/update BOTH languages here in the
    same edit. Never put display text directly in a template.

Some strings contain {placeholders} (filled via t(key, **kwargs)) and a few
contain HTML links — templates render those with the |safe filter.
"""
from __future__ import annotations

LANGS = ("en", "zh")          # en first = default (site root)
HTML_LANG = {"zh": "zh-CN", "en": "en"}

S: dict[str, dict[str, str]] = {
    # ---- base chrome ------------------------------------------------------
    "meta.description": {
        "en": "A quarterly screen of value-oriented, concentrated institutional managers, built from SEC EDGAR 13F filings.",
        "zh": "基于 SEC EDGAR 13F 文件构建的价值型、集中持仓机构管理人季度筛选。",
    },
    "skip": {"en": "Skip to content", "zh": "跳转到正文"},
    "nav.overview": {"en": "Overview", "zh": "总览"},
    "nav.quarter": {"en": "This quarter", "zh": "本季动向"},
    "nav.managers": {"en": "Managers", "zh": "管理人"},
    "nav.stocks": {"en": "Most-held stocks", "zh": "热门持仓"},
    "nav.methodology": {"en": "Methodology", "zh": "方法论"},
    "nav.switch": {"en": "中文", "zh": "EN"},   # label of the OTHER language
    "footer.source": {
        "en": 'Data sourced from <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;type=13F" rel="noopener">SEC EDGAR 13F filings</a>.',
        "zh": '数据来源:<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;type=13F" rel="noopener">SEC EDGAR 13F 文件</a>。',
    },
    "footer.latest": {"en": "Latest quarter:", "zh": "最新季度:"},
    "footer.loaded": {"en": "data loaded", "zh": "数据加载于"},
    "footer.built": {"en": "site built", "zh": "网站构建于"},
    "footer.disclaimer": {
        "en": "For informational purposes only. Not investment advice. 13F filings are disclosed up to 45 days after quarter-end, cover long U.S.-listed positions only, and exclude short positions and most derivatives. Figures are aggregated from public filings and may contain errors.",
        "zh": "本网站仅供参考,不构成投资建议。13F 文件最迟于季度结束后 45 天披露,仅涵盖美国上市的多头持仓,不含空头及多数衍生品。数据汇总自公开文件,可能存在错误。",
    },

    # ---- shared small words ------------------------------------------------
    "chg.new": {"en": "New", "zh": "新建仓"},
    "chg.added": {"en": "Added", "zh": "加仓"},
    "chg.trimmed": {"en": "Trimmed", "zh": "减仓"},
    "chg.exited": {"en": "Exited", "zh": "清仓"},
    "chg.unchanged": {"en": "Unchanged", "zh": "未变"},
    "lapse.aum_below_floor": {"en": "dipped below $2B", "zh": "资产降至 $2B 以下"},
    "lapse.not_concentrated": {"en": "drifted past the concentration limits", "zh": "超出集中度标准"},
    "lapse.below_min_holdings": {"en": "fewer than 3 names", "zh": "持仓不足 3 家"},
    "lapse.mostly_etfs": {"en": "book is now mostly ETFs", "zh": "组合以 ETF 为主"},
    "lapse.too_many_holdings_for_weight": {"en": "top-heavy but holds more than 50 names", "zh": "头部集中但持仓超过 50 家"},
    "lapse.confidential": {"en": "filed confidentially", "zh": "申请保密处理"},
    "lapse.no_disclosure": {"en": "filed without disclosing holdings", "zh": "申报但未披露持仓"},
    "common.aum_names": {"en": "{aum} · {n} names", "zh": "{aum} · 持仓 {n} 家"},
    "common.was_aum_names": {"en": "was {aum} · {n} names", "zh": "原 {aum} · 持仓 {n} 家"},
    "common.none_quarter": {"en": "None this quarter.", "zh": "本季暂无。"},
    "common.see_methodology": {
        "en": 'See the <a href="{root}methodology.html">methodology</a>.',
        "zh": '详见<a href="{root}methodology.html">方法论</a>。',
    },

    # ---- Overview (index) --------------------------------------------------
    "home.title": {"en": "{site} — value-oriented 13F managers, {q}", "zh": "{site} — 价值型 13F 管理人,{q}"},
    "home.eyebrow": {"en": "SEC 13F screen", "zh": "SEC 13F 筛选"},
    "home.h1": {"en": "Where concentrated, value-oriented capital is invested", "zh": "集中持仓的价值型资本流向何处"},
    "home.lede": {
        "en": 'A curated universe of value-investing managers reporting more than $2&nbsp;billion in concentrated U.S. equity portfolios. See the <a href="methodology.html">methodology</a>. Built automatically from public SEC filings.',
        "zh": '一份精选的价值投资管理人名单:其披露的美股集中组合规模超过 $2B。见<a href="methodology.html">方法论</a>。全站由公开 SEC 文件自动生成。',
    },
    "home.kpi.managers": {"en": "Investment managers", "zh": "投资管理人"},
    "home.kpi.managers_sub": {"en": "members of the screened universe", "zh": "筛选名单成员数"},
    "home.kpi.assets": {"en": "Combined assets", "zh": "合计资产"},
    "home.kpi.assets_sub": {"en": "disclosed U.S. long positions", "zh": "披露的美股多头持仓"},
    "home.kpi.median": {"en": "Median holdings", "zh": "持仓数中位数"},
    "home.kpi.median_sub": {"en": "distinct companies per manager", "zh": "每位管理人持有的公司数"},
    "home.kpi.positions": {"en": "Disclosed positions", "zh": "披露持仓笔数"},
    "home.kpi.positions_sub": {"en": "across the screened universe", "zh": "全名单合计"},
    "home.mostheld.h2": {"en": "Most-held stocks", "zh": "热门持仓"},
    "home.mostheld.sub": {"en": "The companies owned by the most members this quarter — a conviction signal (ETF/index positions excluded).", "zh": "本季被最多成员共同持有的公司——信念信号(不含 ETF/指数基金持仓)。"},
    "home.mostheld.all": {"en": "See all &rarr;", "zh": "查看全部 &rarr;"},
    "home.aum.h3": {"en": "Assets under management", "zh": "资产规模分布"},
    "home.aum.hint": {"en": "Distribution of 13F AUM across the screened universe.", "zh": "成员 13F 资产规模(AUM)的分布。"},
    "home.conc.h3": {"en": "Portfolio concentration", "zh": "组合集中度"},
    "home.conc.hint": {"en": "Number of distinct companies held. Admission requires &le;30 (or &le;50 if top-heavy); lapsed members can sit above that.", "zh": "持有公司数量的分布。入选要求 &le;30 家(头部集中时 &le;50 家);暂离标准的成员可能高于该值。"},
    "home.topmgr.h3": {"en": "Top managers by AUM", "zh": "资产规模 Top 10 管理人"},
    "home.topmgr.hint": {"en": "The ten largest members by disclosed 13F assets.", "zh": "按披露 13F 资产排序的前十大成员。"},
    "home.flows.h3": {"en": "Money moves this quarter", "zh": "本季资金动向"},
    "home.flows.hint": {"en": 'Largest estimated net buying and selling — the full story is on the <a href="moves.html">This quarter</a> page.', "zh": '估算净买入与净卖出最大的公司——完整内容见<a href="moves.html">本季动向</a>页。'},
    "home.flows.in": {"en": "Top buys", "zh": "净买入 Top 5"},
    "home.flows.out": {"en": "Top sells", "zh": "净卖出 Top 5"},

    # ---- This quarter (moves) ----------------------------------------------
    "moves.title": {"en": "This quarter's money moves — {site} ({q})", "zh": "本季资金动向 — {site}({q})"},
    "moves.meta": {
        "en": "Where the screened concentrated value managers moved money in {q}: estimated net buying and selling by company, the biggest individual position changes, and membership changes.",
        "zh": "{q} 筛选名单成员的资金动向:按公司估算的净买卖、最大单笔调仓及成员变动。",
    },
    "moves.eyebrow": {"en": "Money moves", "zh": "资金动向"},
    "moves.h1": {"en": "How money moved this quarter", "zh": "本季资金如何流动"},
    "moves.lede": {
        "en": "Estimated net buying and selling across the member universe — computed from <em>share-count</em> changes (so a stock that merely went up in price doesn't look like buying). The same members are compared against their own prior filings; membership changes are listed at the bottom.",
        "zh": "基于<em>股数</em>变化估算的成员净买入与净卖出(股价上涨本身不会被误认成买入)。比较对象是同一批成员各自的上期申报;成员变动列于页面底部。",
    },
    "moves.kpi.compared": {"en": "Members compared", "zh": "参与比较的成员"},
    "moves.kpi.compared_gap": {"en": "of {count} — {n} new member(s) have no prior filing yet", "zh": "共 {count} 名成员,其中 {n} 名新成员尚无上期申报"},
    "moves.kpi.compared_all": {"en": "every member, against their prior filings", "zh": "全部成员,对比各自上期申报"},
    "moves.kpi.in": {"en": "Est. money in", "zh": "估算流入"},
    "moves.kpi.out": {"en": "Est. money out", "zh": "估算流出"},
    "moves.kpi.net": {"en": "Net", "zh": "净额"},
    "moves.in.h2": {"en": "Where money moved in", "zh": "资金流入方向"},
    "moves.in.sub": {"en": "Companies with the largest estimated net buying.", "zh": "估算净买入最大的公司。"},
    "moves.out.h2": {"en": "Where money moved out", "zh": "资金流出方向"},
    "moves.out.sub": {"en": "Companies with the largest estimated net selling.", "zh": "估算净卖出最大的公司。"},
    "moves.th.company": {"en": "Company", "zh": "公司"},
    "moves.th.shares_bought": {"en": "Shares bought", "zh": "净买入股数"},
    "moves.th.shares_sold": {"en": "Shares sold", "zh": "净卖出股数"},
    "moves.th.est_value": {"en": "Est. value", "zh": "估算金额"},
    "moves.th.holders": {"en": "Holders", "zh": "持有人数"},
    "moves.th.manager": {"en": "Manager", "zh": "管理人"},
    "moves.th.bought": {"en": "Bought", "zh": "买入"},
    "moves.th.sold": {"en": "Sold", "zh": "卖出"},
    "moves.th.shares": {"en": "Shares", "zh": "股数"},
    "moves.big.h2": {"en": "Biggest individual moves", "zh": "最大单笔调仓"},
    "moves.big.sub": {"en": "The largest single position changes by any one manager — the quarter's boldest calls.", "zh": "单个管理人最大的持仓变动——本季最大胆的决策。"},
    "moves.mem.h2": {"en": "Membership changes", "zh": "成员变动"},
    "moves.mem.sub": {
        "en": "The universe is a <em>sticky roster</em>: managers join by passing the screen and stay until removed by hand. New members joined this quarter; lapsed members no longer meet the criteria but are <strong>kept by default</strong> pending review.",
        "zh": "成员名单具有<em>粘性</em>:管理人通过筛选即加入,只有人工审核才会移除。新成员为本季加入;暂离标准的成员当前不满足筛选条件,但<strong>默认保留</strong>、待审核。",
    },
    "moves.mem.new": {"en": "New members ({n})", "zh": "新成员({n})"},
    "moves.mem.lapsed": {"en": "Lapsed — kept pending review ({n})", "zh": "暂离标准——保留待审核({n})"},
    "moves.mem.lapsed_none": {"en": "Every member meets the criteria this quarter.", "zh": "本季全部成员均符合标准。"},
    "moves.mem.left": {"en": "Left ({n})", "zh": "已移除({n})"},
    "moves.footnote": {
        "en": 'How these numbers are estimated: net flow = change in shares × the position\'s implied share price (disclosed value ÷ shares), summed across members present in both quarters. 13F data is long-only U.S. positions with a 45-day lag. See the <a href="{root}methodology.html">methodology</a>.',
        "zh": '估算方式:净流量 = 股数变化 × 该持仓的隐含股价(披露市值 ÷ 股数),对两个季度均在名单中的成员求和。13F 数据仅含美股多头持仓,最长有 45 天延迟。详见<a href="{root}methodology.html">方法论</a>。',
    },

    # ---- Managers directory (funds) ----------------------------------------
    "dir.title": {"en": "Managers — {site} ({q})", "zh": "管理人 — {site}({q})"},
    "dir.eyebrow": {"en": "Directory", "zh": "名录"},
    "dir.h1": {"en": "Universe members", "zh": "名单成员"},
    "dir.lede": {
        "en": "Every member of the screened universe — managers join by passing the screen and stay until reviewed out, so a few currently sit below the criteria (their pages say so). Search and sort; click any name for its full portfolio and quarter-over-quarter moves.",
        "zh": "筛选名单的全部成员——管理人通过筛选加入并保留至人工移除,因此少数成员当前低于标准(其页面会注明)。支持搜索与排序;点击任一名称查看完整组合与季度调仓。",
    },
    "dir.search": {"en": "Search manager name…", "zh": "搜索管理人名称…"},
    "dir.search_aria": {"en": "Search managers", "zh": "搜索管理人"},
    "dir.shown": {"en": "shown", "zh": "家显示中"},
    "dir.csv": {"en": "Download CSV", "zh": "下载 CSV"},
    "dir.th.manager": {"en": "Manager", "zh": "管理人"},
    "dir.th.aum": {"en": "AUM", "zh": "资产规模"},
    "dir.th.holdings": {"en": "# Holdings", "zh": "持仓公司数"},
    "dir.th.positions": {"en": "# Positions", "zh": "持仓笔数"},
    "dir.th.filed": {"en": "Filed", "zh": "申报日期"},

    # ---- Manager deep-dive (fund) ------------------------------------------
    "fund.title": {"en": "{name} — 13F holdings", "zh": "{name} — 13F 持仓"},
    "fund.meta": {
        "en": "{name} 13F holdings and quarter-over-quarter moves across the last {n} reported quarters, built from SEC EDGAR filings.",
        "zh": "{name} 最近 {n} 个季度的 13F 持仓与季度调仓,基于 SEC EDGAR 文件构建。",
    },
    "fund.back": {"en": "&larr; All managers", "zh": "&larr; 全部管理人"},
    "fund.aum.h2": {"en": "Assets under management over time", "zh": "资产规模变化"},
    "fund.aum.sub": {"en": "Disclosed 13F assets for every quarter on record ({n}) — including quarters where the manager didn't meet the screen.", "zh": "历史各季度披露的 13F 资产(共 {n} 期)——含未达筛选标准的季度。"},
    "fund.aum.aria": {"en": "AUM over time", "zh": "资产规模随时间变化"},
    "fund.byq.h2": {"en": "Portfolio by quarter", "zh": "分季度组合"},
    "fund.byq.sub": {"en": "Pick a quarter to see that filing's holdings and what changed since the quarter before.", "zh": "选择季度,查看该期持仓及相对上一季度的变化。"},
    "fund.byq.offnote": {
        "en": "○ marks quarters shown for history where the manager didn't meet the selection criteria (&gt;${min_aum_b}B AUM and either &le;{max_holdings} issuers or top {top_n} &ge;{top_n_min_pct}% of AUM with &le;{max_holdings_weighted} issuers).",
        "zh": "○ 标记的季度仅作历史展示,当期未达筛选标准(资产 &gt;${min_aum_b}B,且持仓 &le;{max_holdings} 家,或前 {top_n} 大持仓 &ge;{top_n_min_pct}% 且 &le;{max_holdings_weighted} 家)。",
    },
    "fund.off_chip_title": {"en": "Shown for history — did not meet the selection criteria this quarter", "zh": "仅作历史展示——该季度未达筛选标准"},
    "fund.stat.aum": {"en": "13F AUM", "zh": "13F 资产"},
    "fund.stat.companies": {"en": "Companies", "zh": "公司数"},
    "fund.stat.positions": {"en": "Positions", "zh": "持仓笔数"},
    "fund.stat.topn": {"en": "Top {n} weight", "zh": "前 {n} 大权重"},
    "fund.stat.filed": {"en": "Filed", "zh": "申报"},
    "fund.callout.member": {
        "en": 'This filing didn\'t meet the screen\'s criteria in {q}{reason} — but as a member of the universe roster, the manager stays listed by default pending review (see the <a href="{root}methodology.html">methodology</a>).',
        "zh": '本期申报在 {q} 未达筛选标准{reason}——但作为名单成员,默认继续展示、待审核(见<a href="{root}methodology.html">方法论</a>)。',
    },
    "fund.callout.history": {
        "en": "Shown for history. This filing didn't meet the selection criteria in {q}{reason}, so the manager isn't part of the screened universe — its filings are kept so the timeline and quarter-over-quarter moves stay continuous.",
        "zh": "仅作历史展示。本期申报在 {q} 未达筛选标准{reason},该管理人不属于当期筛选名单——保留其申报以保证时间线与季度对比的连续。",
    },
    "fund.holdings.h3": {"en": "Holdings &mdash; {q}", "zh": "持仓 &mdash; {q}"},
    "fund.holdings.sub": {"en": "{n} reported positions, largest first.", "zh": "共 {n} 笔披露持仓,按市值从大到小排序。"},
    "fund.holdings.sec": {"en": "View original {form} filing on SEC EDGAR&nbsp;↗", "zh": "在 SEC EDGAR 查看原始 {form} 文件&nbsp;↗"},
    "fund.th.company": {"en": "Company", "zh": "公司"},
    "fund.th.pct": {"en": "% of portfolio", "zh": "组合占比"},
    "fund.th.value": {"en": "Value", "zh": "市值"},
    "fund.th.shares": {"en": "Shares", "zh": "股数"},
    "fund.th.class": {"en": "Class", "zh": "类别"},
    "fund.moves.h3": {"en": "Quarter-over-quarter moves &mdash; {q}", "zh": "季度调仓 &mdash; {q}"},
    "fund.moves.sub": {"en": "Changes in share count versus {prev} — what the manager actually bought or sold.", "zh": "相对 {prev} 的股数变化——管理人实际的买卖动作。"},
    "fund.moves.prior": {"en": "the prior filing", "zh": "上一期申报"},
    "fund.th.change": {"en": "Change", "zh": "变动"},
    "fund.th.now": {"en": "Value now", "zh": "现市值"},
    "fund.th.before": {"en": "Value before", "zh": "前市值"},
    "fund.th.delta": {"en": "&Delta; Value", "zh": "市值变化"},
    "fund.moves.none": {"en": "No position changes versus {prev} — the portfolio was held steady.", "zh": "相对 {prev} 无持仓变化——组合保持不变。"},
    "fund.moves.earliest": {"en": "This is the earliest quarter on record for this manager, so there's no prior filing to compare against yet. As new quarters load, moves will appear here.", "zh": "这是该管理人记录中最早的季度,暂无更早的申报可比。新季度载入后,调仓将显示于此。"},

    # ---- Most-held stocks (stocks) -----------------------------------------
    "stocks.title": {"en": "Most-held stocks — {site} ({q})", "zh": "热门持仓 — {site}({q})"},
    "stocks.eyebrow": {"en": "Conviction", "zh": "信念"},
    "stocks.h1": {"en": "Most-held stocks", "zh": "热门持仓"},
    "stocks.lede": {
        "en": "The companies owned by the most universe members this quarter. A stock held by many concentrated, value-oriented investors is a strong conviction signal. ETF and index-fund positions are excluded — they're parked cash, not stock-picking.",
        "zh": "本季被最多名单成员持有的公司。被众多集中持仓的价值型投资人共同持有,是强烈的信念信号。不含 ETF 与指数基金持仓——那是停泊的资金,不是选股。",
    },
    "stocks.search": {"en": "Search company…", "zh": "搜索公司…"},
    "stocks.search_aria": {"en": "Search stocks", "zh": "搜索股票"},
    "stocks.th.company": {"en": "Company", "zh": "公司"},
    "stocks.th.nmgrs": {"en": "# Managers holding", "zh": "持有管理人数"},
    "stocks.th.value": {"en": "Combined value", "zh": "合计市值"},
    "stocks.th.avgpct": {"en": "Avg % of portfolio", "zh": "平均组合占比"},

    # ---- Stock page ---------------------------------------------------------
    "stock.title": {"en": "{issuer} — 13F holders ({q})", "zh": "{issuer} — 13F 持有人({q})"},
    "stock.meta": {
        "en": "Which screened, concentrated managers hold {issuer}, how each position changed quarter-over-quarter, and the combined position size over the last {n} quarters — from SEC EDGAR 13F filings.",
        "zh": "哪些筛选名单成员持有 {issuer}、各持仓的季度变化,以及最近 {n} 个季度的合计仓位——基于 SEC EDGAR 13F 文件。",
    },
    "stock.back": {"en": "&larr; Most-held stocks", "zh": "&larr; 热门持仓"},
    "stock.held_by": {"en": "Held by {n} of {total} managers", "zh": "{total} 家管理人中 {n} 家持有"},
    "stock.exited_badge": {"en": "Fully exited in {q}", "zh": "{q} 已全部清仓"},
    "stock.lede": {"en": "Combined disclosed 13F position of <strong>{value}</strong> ({shares} shares) across the screened universe in {q}.", "zh": "{q} 名单成员合计披露持仓 <strong>{value}</strong>({shares} 股)。"},
    "stock.lede_exited": {"en": "No universe member holds {issuer} as of {q} — every position was sold since {prev}. The exit is the story on this page.", "zh": "截至 {q},已无成员持有 {issuer}——所有仓位自 {prev} 以来全部卖出。本页讲述的正是这次清仓。"},
    "stock.trend.h2": {"en": "Combined position over time", "zh": "合计仓位变化"},
    "stock.trend.sub": {"en": "Total disclosed 13F value, total shares held, and the number of screened managers holding {issuer}, over the last {n} quarters. Shares are the cleanest accumulation signal — value also moves with the stock price.", "zh": "最近 {n} 个季度:持有 {issuer} 的合计披露市值、合计持股数与成员数。股数是最干净的增减仓信号——市值还会随股价波动。"},
    "stock.card.value": {"en": "Combined value", "zh": "合计市值"},
    "stock.card.shares": {"en": "Total shares held", "zh": "合计持股数"},
    "stock.card.holders": {"en": "Managers holding", "zh": "持有成员数"},
    "stock.aria.value": {"en": "Combined value over time", "zh": "合计市值随时间变化"},
    "stock.aria.shares": {"en": "Total shares held over time", "zh": "合计持股数随时间变化"},
    "stock.aria.holders": {"en": "Number of managers holding over time", "zh": "持有成员数随时间变化"},
    "stock.tip.shares": {"en": "{label}: {value} shares", "zh": "{label}:{value} 股"},
    "stock.tip.holders_one": {"en": "{label}: {value} manager", "zh": "{label}:{value} 家管理人"},
    "stock.tip.holders": {"en": "{label}: {value} managers", "zh": "{label}:{value} 家管理人"},
    "stock.trend.short": {"en": "Not enough quarters on record yet to chart a trend.", "zh": "记录的季度尚不足以绘制趋势。"},
    "stock.changed.h2": {"en": "What changed since {prev}", "zh": "自 {prev} 以来的变化"},
    "stock.changed.h2_noprev": {"en": "What changed", "zh": "变化"},
    "stock.earliest": {"en": "This is the earliest quarter on record, so there's no prior filing to compare against yet.", "zh": "这是记录中最早的季度,暂无更早的申报可比。"},
    "stock.buyers.h3": {"en": "New buyers", "zh": "新买入"},
    "stock.buyers.none": {"en": "No new buyers this quarter.", "zh": "本季无新买入。"},
    "stock.exits.h3": {"en": "Exited", "zh": "已清仓"},
    "stock.exits.none": {"en": "No managers fully exited this quarter.", "zh": "本季无人全部清仓。"},
    "stock.was": {"en": "was {value}", "zh": "原 {value}"},
    "stock.holders.h2": {"en": "Current holders &mdash; {q}", "zh": "当前持有人 &mdash; {q}"},
    "stock.holders.none": {"en": 'None — every member that held {issuer} has sold out. The sellers are listed under "Exited" above.', "zh": "无——曾持有 {issuer} 的成员均已卖出,卖出者见上方「已清仓」。"},
    "stock.holders.sub": {"en": "Every screened manager holding {issuer}, largest position first. Change vs {prev} is by share count — what the manager actually bought or sold.", "zh": "持有 {issuer} 的全部成员,按持仓市值排序。「变动」为相对 {prev} 的股数变化——实际买卖动作。"},
    "stock.th.manager": {"en": "Manager", "zh": "管理人"},
    "stock.th.value": {"en": "Position value", "zh": "持仓市值"},
    "stock.th.pct": {"en": "% of their portfolio", "zh": "占其组合 %"},
    "stock.th.shares": {"en": "Shares", "zh": "股数"},
    "stock.th.change": {"en": "Change", "zh": "变动"},
    "stock.th.delta": {"en": "&Delta; Value", "zh": "市值变化"},
    "stock.footnote": {
        "en": '13F discloses long U.S.-listed positions only, reported with up to a 45-day lag. See the <a href="{root}methodology.html">methodology</a> for details.',
        "zh": '13F 仅披露美国上市的多头持仓,且最长有 45 天延迟。详见<a href="{root}methodology.html">方法论</a>。',
    },

    # ---- Methodology --------------------------------------------------------
    "method.title": {"en": "Methodology — {site}", "zh": "方法论 — {site}"},
    "method.eyebrow": {"en": "About the data", "zh": "关于数据"},
    "method.h1": {"en": "Methodology", "zh": "方法论"},
    "method.lede": {"en": "How this screen is built, what it includes, and the limitations you should keep in mind.", "zh": "本筛选如何构建、包含什么,以及应当注意的局限。"},
    "method.screen.h2": {"en": "The screen", "zh": "筛选标准"},
    "method.screen.intro": {"en": "Every quarter we read all Form 13F filings from SEC EDGAR and keep only institutions that are large <em>and</em> concentrated, to isolate high-conviction, value-oriented managers. A filing qualifies when it has:", "zh": "每个季度,我们读取 SEC EDGAR 上的全部 13F 申报,只保留规模大<em>且</em>持仓集中的机构,以筛出高信念的价值型管理人。一份申报需同时满足:"},
    "method.screen.b1": {"en": "<strong>More than ${min_aum_b}&nbsp;billion</strong> in disclosed 13F assets, <strong>and</strong>", "zh": "披露 13F 资产<strong>超过 ${min_aum_b}B</strong>,<strong>且</strong>"},
    "method.screen.b2": {"en": "at least <strong>{min_holdings} distinct companies</strong> (so single- and double-stock vehicles — operating companies reporting one strategic stake — are excluded), <strong>and</strong>", "zh": "持有至少 <strong>{min_holdings} 家不同公司</strong>(排除只申报一两笔战略持股的运营公司等单一持仓主体),<strong>且</strong>"},
    "method.screen.b3": {"en": "less than <strong>{max_etf_pct}% of assets in ETFs or index funds</strong> (a mostly-ETF book is a passive basket, not a stock-picker), <strong>and</strong>", "zh": "ETF 与指数基金持仓<strong>低于资产的 {max_etf_pct}%</strong>(以 ETF 为主的组合是被动篮子,不是选股),<strong>且</strong>"},
    "method.screen.b4": {"en": "is concentrated by <strong>either</strong> measure:", "zh": "满足以下<strong>任一</strong>集中度标准:"},
    "method.screen.b4a": {"en": "<strong>{max_holdings} or fewer distinct companies</strong> held, <strong>or</strong>", "zh": "持有<strong>不超过 {max_holdings} 家</strong>不同公司,<strong>或</strong>"},
    "method.screen.b4b": {"en": "its <strong>top {top_n} positions make up at least {top_n_min_pct}%</strong> of disclosed AUM, while still holding <strong>{max_holdings_weighted} or fewer distinct companies</strong>.", "zh": "<strong>前 {top_n} 大持仓占披露资产至少 {top_n_min_pct}%</strong>,且总持仓仍<strong>不超过 {max_holdings_weighted} 家</strong>。"},
    "method.screen.callout": {"en": "A large book paired with either a short holdings list or a heavy top-10 weighting is the signature of a manager who concentrates capital in their best ideas, rather than indexing broadly. The second test catches managers who carry a modest tail of small positions but still run a genuinely concentrated portfolio — while the {max_holdings_weighted}-company cap on that test keeps out broad mutual-fund complexes that merely happen to be top-heavy.", "zh": "大规模资产搭配精简的持仓清单或极高的前十大权重,正是把资本集中投向最佳想法、而非广泛指数化的管理人特征。第二条标准照顾到带少量小仓位长尾、但本质上仍高度集中的管理人——而该标准的 {max_holdings_weighted} 家上限,把那些只是头部偏重的大型基金复合体挡在门外。"},
    "method.sticky.h2": {"en": "Membership is sticky", "zh": "成员资格具有粘性"},
    "method.sticky.p": {
        "en": 'The criteria above are an <strong>admission test</strong>, not a quarterly eviction rule. A manager that qualifies joins the universe and <strong>stays by default</strong> — a great manager having a soft quarter (assets dipping under the floor, or drifting a few names past the concentration line) shouldn\'t vanish from the record. Members that no longer meet the criteria are marked as <em>lapsed</em> on the <a href="moves.html">This quarter</a> page, with the reason, and are only removed by an explicit editorial decision — every such decision is recorded publicly in the project\'s history. This means the universe count can exceed the number of filers currently passing the screen.',
        "zh": '上述标准是<strong>入选测试</strong>,而非每季度的淘汰规则。管理人一旦达标即加入名单并<strong>默认保留</strong>——优秀的管理人遇到一个疲软季度(资产暂时跌破门槛、或持仓数略超集中度线)不应从记录中消失。不再满足标准的成员会在<a href="moves.html">本季动向</a>页被标记为<em>暂离标准</em>并注明原因,只有明确的编辑决定才会将其移除——每个此类决定都公开记录在项目历史中。因此,名单成员数可能超过当前通过筛选的申报机构数。',
    },
    "method.history.h2": {"en": "Manager deep-dives keep full history", "zh": "管理人页保留完整历史"},
    "method.history.p": {"en": "Whether a manager qualifies can change from quarter to quarter — a book can drift just over or under the holdings line. Once a manager qualifies in <em>any</em> of the recent quarters we track, we keep its filings for <em>all</em> of those quarters so each deep-dive shows a continuous timeline and accurate quarter-over-quarter moves. Quarters where the manager didn't meet the criteria are clearly marked (with a ○).", "zh": "管理人是否达标会随季度变化——组合可能在持仓数门槛上下波动。只要管理人在我们跟踪的<em>任一</em>近期季度达标,我们就保留其<em>全部</em>季度的申报,使每个管理人页都有连续的时间线和准确的季度对比。未达标准的季度会清晰标注(○)。"},
    "method.types.h2": {"en": "Filer types", "zh": "申报机构类型"},
    "method.types.p": {"en": "13F filings come from many kinds of institutions, not just stock-pickers. We label each filer by type and <strong>exclude the kinds that aren't fundamental, concentrated fund managers</strong>: market-makers / trading desks, operating and holding companies (corporations reporting strategic stakes), sovereign wealth funds, central banks and pensions, and banks / insurers. <strong>Private-equity / venture firms and foundations / endowments are kept</strong>, since some run genuinely concentrated equity books. Types come from a transparent name heuristic with <em>per-filer overrides</em>; on the site, every member is presented simply as an investment manager. The heuristic is approximate; corrections are welcome.", "zh": "提交 13F 的机构种类繁多,并非都是选股者。我们为每个申报机构标注类型,并<strong>排除不属于基本面集中型基金管理人的类别</strong>:做市商/交易台、运营与控股公司(申报战略持股的企业)、主权财富基金、央行与养老金、银行/保险。<strong>私募股权/风投及基金会/捐赠基金予以保留</strong>,因为其中一些确实运作高度集中的股票组合。类型来自透明的名称启发式并辅以<em>逐个覆盖</em>;在网站上,所有成员一律以投资管理人呈现。该启发式只是近似,欢迎指正。"},
    "method.calc.h2": {"en": "How figures are computed", "zh": "数据如何计算"},
    "method.calc.b1": {"en": "<strong>AUM</strong> is the sum of a filer's disclosed long positions. Filings that report values in thousands (before 2023) are normalized to whole dollars.", "zh": "<strong>AUM(资产规模)</strong>为披露多头持仓的市值之和。2023 年前以千美元为单位申报的文件已统一换算为美元。"},
    "method.calc.b2": {"en": "<strong>Holdings</strong> are aggregated by company (the first six CUSIP digits), so multiple share classes or shared-discretion rows collapse into one position.", "zh": "<strong>持仓</strong>按公司汇总(CUSIP 前六位),因此多个股份类别或共同决策行会合并为一笔仓位。"},
    "method.calc.b3": {"en": "<strong>Quarter-over-quarter moves</strong> compare share counts against the manager's previous screened quarter, classifying each position as new, added, trimmed, or exited.", "zh": "<strong>季度调仓</strong>将股数与该管理人上一期相比,把每笔仓位归类为新建仓、加仓、减仓或清仓。"},
    "method.calc.b4": {"en": "<strong>Amended filings</strong> (13F-HR/A): a <em>restatement</em> amendment supersedes the original for that period, but a partial “new holdings” amendment (one that only adds a few positions) does not displace the original filing.", "zh": "<strong>修正申报</strong>(13F-HR/A):<em>重述型</em>修正会取代该期原件;而仅补充少量持仓的「新增持仓」型部分修正不会取代原始申报。"},
    "method.cadence.h2": {"en": "Update cadence", "zh": "更新节奏"},
    "method.cadence.p": {"en": "13F filings are due 45 days after each quarter-end. Shortly after each deadline (mid-February, May, August, and November) the site automatically ingests the new quarter and rebuilds.", "zh": "13F 须在每季度结束后 45 天内申报。每个截止日(2 月、5 月、8 月、11 月中旬)之后不久,本站会自动载入新季度并重建。"},
    "method.limits.h2": {"en": "Limitations", "zh": "局限"},
    "method.limits.b1": {"en": "13F discloses <strong>long U.S.-listed positions only</strong> — no short positions, cash, non-U.S. listings, or most derivatives.", "zh": "13F <strong>仅披露美国上市的多头持仓</strong>——不含空头、现金、非美上市及多数衍生品。"},
    "method.limits.b2": {"en": "Data is reported with up to a <strong>45-day lag</strong>, so it is not real-time.", "zh": "数据最长有 <strong>45 天延迟</strong>,并非实时。"},
    "method.limits.b3": {"en": "Managers may obtain <strong>confidential treatment</strong> to omit holdings; such filings are excluded from the screen rather than counted as concentrated.", "zh": "管理人可申请<strong>保密处理</strong>而暂不披露持仓;此类申报会被排除在筛选之外,而不会被误认为高度集中。"},
    "method.limits.b4": {"en": "Figures are parsed from public filings and may contain errors.", "zh": "数据解析自公开文件,可能存在错误。"},
    "method.advice": {"en": "<strong>Not investment advice.</strong> This site is for informational and educational purposes only. Always do your own research.", "zh": "<strong>非投资建议。</strong>本网站仅用于信息与教育目的。请务必自行研究。"},
}


def t(key: str, lang: str, **kwargs) -> str:
    """Translate `key` into `lang`, applying {placeholder} substitutions.

    Raises KeyError on a missing key or language — by design, so a template
    referencing an untranslated string fails the build instead of shipping a
    half-translated page.
    """
    s = S[key][lang]
    return s.format(**kwargs) if kwargs else s
