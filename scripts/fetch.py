#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 投顾持仓看板 —— 每日净值抓取与计算

数据源：雪球蛋卷公开接口（无需凭证）
  https://danjuanfunds.com/djapi/fund/nav/history/<code>
输出：docs/data.json（供 GitHub Pages 前端读取）

只用标准库，避免依赖安装问题。
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLDINGS_PATH = os.path.join(ROOT, "holdings.csv")
OUT_PATH = os.path.join(ROOT, "docs", "data.json")

CST = timezone(timedelta(hours=8))
NAV_API = "https://danjuanfunds.com/djapi/fund/nav/history/{code}?page=1&size=8"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 净值天然滞后一个交易日的品种（QDII）
QDII = {"023074", "006328", "013309"}

GROUP_TITLES = {
    "A": "均衡十字星投顾组合",
    "B": "组合外自持",
}
GROUP_NOTES = {
    "A": "10 只等权，每只占组合 10%，不单独卖出",
    "B": "可变现部分，调仓从这里出",
}


# ---------------------------------------------------------------- 工具函数

def is_workday(d: date) -> bool:
    return d.weekday() < 5


def prev_workday(d: date) -> date:
    """严格早于 d 的上一个工作日"""
    cur = d - timedelta(days=1)
    while not is_workday(cur):
        cur -= timedelta(days=1)
    return cur


def workdays_between(a: date, b: date) -> int:
    """a 之后到 b（含 b）之间的工作日数量"""
    if b <= a:
        return 0
    n, cur = 0, a + timedelta(days=1)
    while cur <= b:
        if is_workday(cur):
            n += 1
        cur += timedelta(days=1)
    return n


def target_date(now: datetime) -> date:
    """当前应当已公布到哪一天的净值"""
    today = now.date()
    if is_workday(today) and now.hour >= 19:
        return today
    return prev_workday(today) if is_workday(today) or True else today


def fetch_json(url: str, retries: int = 3) -> dict:
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://danjuanfunds.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if i < retries - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"请求失败 {url}: {last_err}")


def load_holdings() -> list[dict]:
    with open(HOLDINGS_PATH, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        code = str(r["代码"]).strip()
        if not code:
            continue
        out.append(
            {
                "code": code,
                "name": str(r["名称"]).strip(),
                "shares": float(r["份额"]),
                "cost": float(r["单位成本"]),
                "group": str(r.get("分组", "B")).strip().upper() or "B",
            }
        )
    return out


def load_previous_history() -> list[dict]:
    if not os.path.exists(OUT_PATH):
        return []
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            old = json.load(f)
        return old.get("history", []) or []
    except Exception:
        return []


def load_previous_navs() -> dict[str, dict]:
    """上次成功抓到的净值，用于单只抓取失败时兜底"""
    if not os.path.exists(OUT_PATH):
        return {}
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            old = json.load(f)
        return {h["code"]: h for h in old.get("holdings", [])}
    except Exception:
        return {}


# ---------------------------------------------------------------- 主流程

def main() -> int:
    now = datetime.now(CST)
    tgt = target_date(now)
    holdings = load_holdings()
    prev_navs = load_previous_navs()
    prev_history = load_previous_history()

    print(f"[{now:%Y-%m-%d %H:%M}] 目标净值日 {tgt}，持仓 {len(holdings)} 只")

    records = []
    failures = []

    for h in holdings:
        code = h["code"]
        nav = nav_date = day_pct = None
        source = "蛋卷"
        try:
            data = fetch_json(NAV_API.format(code=code))
            items = (data.get("data") or {}).get("items") or []
            if not items:
                raise ValueError("接口返回空 items")
            top = items[0]
            nav = float(top["nav"])
            nav_date = datetime.strptime(top["date"], "%Y-%m-%d").date()
            day_pct = float(top["percentage"]) if top.get("percentage") not in (None, "") else 0.0
        except Exception as e:
            failures.append((code, str(e)))
            cached = prev_navs.get(code)
            if cached:
                nav = cached.get("nav")
                nav_date = (
                    datetime.strptime(cached["nav_date"], "%Y-%m-%d").date()
                    if cached.get("nav_date")
                    else None
                )
                day_pct = 0.0
                source = "缓存(本次抓取失败)"
            else:
                nav = None
        finally:
            time.sleep(0.35)

        shares = h["shares"]
        cost_value = shares * h["cost"]

        if nav is None:
            records.append(
                {
                    **h,
                    "nav": None,
                    "nav_date": None,
                    "value": None,
                    "cost_value": round(cost_value, 2),
                    "pnl": None,
                    "pnl_pct": None,
                    "weight": None,
                    "day_pct": None,
                    "day_pnl": None,
                    "lag": None,
                    "source": source,
                    "counted": False,
                }
            )
            continue

        value = shares * nav
        pnl = value - cost_value

        # 判断这份净值能不能算作「当日」
        lag = workdays_between(nav_date, tgt)
        counted = False
        if nav_date == tgt:
            counted = True
            lag = 0
        elif code in QDII and nav_date == prev_workday(tgt):
            counted = True
            lag = 1
        if source.startswith("缓存"):
            counted = False

        day_pnl = None
        if counted and day_pct is not None:
            # 用日增长率反推当日盈亏，比两位小数净值互减更精确
            denom = 1 + day_pct / 100.0
            day_pnl = value - value / denom if denom else None

        records.append(
            {
                **h,
                "nav": round(nav, 4),
                "nav_date": nav_date.strftime("%Y-%m-%d"),
                "value": round(value, 2),
                "cost_value": round(cost_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl / cost_value * 100, 2) if cost_value else None,
                "weight": None,
                "day_pct": round(day_pct, 2) if day_pct is not None else None,
                "day_pnl": round(day_pnl, 2) if day_pnl is not None else None,
                "lag": lag,
                "source": source,
                "counted": counted,
            }
        )

    total_value = round(sum(r["value"] or 0 for r in records), 2)
    total_cost = round(sum(r["cost_value"] or 0 for r in records), 2)
    total_pnl = round(total_value - total_cost, 2)

    for r in records:
        if r["value"] and total_value:
            r["weight"] = round(r["value"] / total_value * 100, 2)

    counted = [r for r in records if r["counted"]]
    day_pnl = round(sum(r["day_pnl"] or 0 for r in counted), 2)
    base_value = round(sum((r["value"] or 0) for r in counted), 2)
    day_pct = round(day_pnl / (base_value - day_pnl) * 100, 2) if base_value - day_pnl else 0.0

    up = sum(1 for r in counted if (r["day_pct"] or 0) > 0)
    down = sum(1 for r in counted if (r["day_pct"] or 0) < 0)
    flat = len(counted) - up - down

    groups = {}
    for g in ("A", "B"):
        members = [r for r in records if r["group"] == g]
        gv = round(sum(r["value"] or 0 for r in members), 2)
        gc = round(sum(r["cost_value"] or 0 for r in members), 2)
        gp = round(gv - gc, 2)
        gpday = round(sum(r["day_pnl"] or 0 for r in members), 2)
        groups[g] = {
            "title": GROUP_TITLES.get(g, g),
            "note": GROUP_NOTES.get(g, ""),
            "count": len(members),
            "value": gv,
            "cost": gc,
            "pnl": gp,
            "pnl_pct": round(gp / gc * 100, 2) if gc else None,
            "day_pnl": gpday,
            "weight": round(gv / total_value * 100, 2) if total_value else None,
        }

    lagging = [
        {
            "code": r["code"],
            "name": r["name"],
            "nav_date": r["nav_date"],
            "lag": r["lag"],
        }
        for r in records
        if r["lag"] and r["lag"] > 0
    ]

    # 历史曲线：同一天只保留最新一份
    hist_date = tgt.strftime("%Y-%m-%d")
    history = [h for h in prev_history if h.get("date") != hist_date]
    if total_value:
        history.append(
            {
                "date": hist_date,
                "value": total_value,
                "pnl": total_pnl,
                "day_pnl": day_pnl,
            }
        )
    history.sort(key=lambda x: x["date"])
    history = history[-250:]

    result = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": tgt.strftime("%Y-%m-%d"),
        "today": now.strftime("%Y-%m-%d"),
        "is_workday": is_workday(now.date()),
        "summary": {
            "total_value": total_value,
            "total_cost": total_cost,
            "total_pnl": total_pnl,
            "total_pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost else None,
            "day_pnl": day_pnl,
            "day_pnl_pct": day_pct,
            "counted": len(counted),
            "total": len(records),
            "up": up,
            "down": down,
            "flat": flat,
            "no_new_nav": len(counted) == 0,
        },
        "groups": groups,
        "holdings": sorted(records, key=lambda r: (r["group"], -(r["value"] or 0))),
        "lagging": lagging,
        "failures": [{"code": c, "error": e} for c, e in failures],
        "history": history,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    print(f"总市值 ¥{total_value:,.2f}｜累计 {total_pnl:+,.2f}｜当日 {day_pnl:+,.2f}")
    print(f"计入当日 {len(counted)}/{len(records)} 只，滞后 {len(lagging)} 只，抓取失败 {len(failures)} 只")
    for c, e in failures:
        print(f"  ! {c} {e}")
    print(f"已写入 {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
