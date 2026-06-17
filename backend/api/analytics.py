"""效果分析 API — 从 job / application 表聚合真实数据。"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from .deps import get_session

router = APIRouter(tags=["效果分析"])

# 岗位标题关键词分类（顺序即优先级）
_CATEGORIES = [
    ("AI/Agent工程师", ["agent", "llm", "大模型", "ai工程", "算法", "nlp", "机器学习"]),
    ("Python后端",     ["python", "fastapi", "django", "flask"]),
    ("全栈开发",       ["全栈", "full stack", "fullstack"]),
    ("前端开发",       ["前端", "frontend", "react", "vue", "next.js"]),
    ("数据工程",       ["数据工程", "data engineer", "etl", "hadoop", "spark"]),
    ("Java后端",       ["java", "spring"]),
]

COLORS = ["var(--green)", "var(--blue)", "var(--amber)", "#A855F7", "#EC4899", "#14B8A6"]


def _classify(title: str) -> str:
    t = title.lower()
    for cat, kws in _CATEGORIES:
        if any(kw in t for kw in kws):
            return cat
    return "其他"


@router.get("/analytics", summary="效果分析聚合数据")
async def get_analytics(
    time_range: str = Query("30d", alias="range", pattern="^(7d|30d|all)$"),
    session: AsyncSession = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    if time_range == "7d":
        start: Optional[datetime] = now - timedelta(days=7)
        days = 7
    elif time_range == "30d":
        start = now - timedelta(days=30)
        days = 30
    else:
        start = None
        days = None

    # SQLite 存储 datetime 格式为 "YYYY-MM-DD HH:MM:SS"（空格分隔，无时区）
    # isoformat() 含 "T" 和 "+00:00"，字符串比较时 "T" > " "，会错误排除近期数据
    fmt = start.strftime("%Y-%m-%d %H:%M:%S") if start else None
    job_where  = f"WHERE scraped_at >= '{fmt}'" if fmt else ""
    app_where2 = f"WHERE sent_at    >= '{fmt}'" if fmt else ""

    # ── 汇总指标 ────────────────────────────────────────────────
    r = (await session.execute(text(f"""
        SELECT
            COUNT(*)                                                    AS total_scraped,
            SUM(status IN ('SENT','PENDING_SEND'))                      AS total_sent,
            SUM(status = 'SKIPPED' OR status = 'FAILED')               AS total_skipped,
            SUM(status = 'PENDING')                                     AS pending,
            SUM(status = 'MATCHED')                                     AS matched,
            ROUND(AVG(CASE WHEN score > 0 THEN score END), 1)          AS avg_score
        FROM job {job_where}
    """))).mappings().first()

    total_scraped  = int(r["total_scraped"]  or 0)
    total_sent     = int(r["total_sent"]     or 0)
    total_skipped  = int(r["total_skipped"]  or 0)
    avg_score      = float(r["avg_score"]    or 0)
    pending        = int(r["pending"]        or 0)
    matched        = int(r["matched"]        or 0)

    # ── 每日趋势（scraped_at & sent_at 按天聚合）───────────────
    daily_scraped_rows = (await session.execute(text(f"""
        SELECT strftime('%Y-%m-%d', scraped_at) AS day, COUNT(*) AS cnt
        FROM job {job_where}
        GROUP BY day ORDER BY day
    """))).mappings().all()

    daily_sent_rows = (await session.execute(text(f"""
        SELECT strftime('%Y-%m-%d', sent_at) AS day, COUNT(*) AS cnt
        FROM application {app_where2}
        GROUP BY day ORDER BY day
    """))).mappings().all()

    scraped_map = {r["day"]: int(r["cnt"]) for r in daily_scraped_rows}
    sent_map    = {r["day"]: int(r["cnt"]) for r in daily_sent_rows}

    if days and scraped_map:
        # 生成连续日期序列
        all_days = [(now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d") for i in range(days)]
    elif scraped_map:
        # all 模式：取实际有数据的日期范围
        all_days_set = sorted(set(scraped_map) | set(sent_map))
        all_days = all_days_set if all_days_set else []
    else:
        all_days = []

    daily = [
        {"date": d, "scraped": scraped_map.get(d, 0), "sent": sent_map.get(d, 0)}
        for d in all_days
    ]

    # ── 岗位类别分布 ────────────────────────────────────────────
    title_rows = (await session.execute(text(f"""
        SELECT title, status FROM job {job_where}
    """))).mappings().all()

    cat_total: dict[str, int] = {}
    cat_sent:  dict[str, int] = {}
    for row in title_rows:
        cat = _classify(row["title"] or "")
        cat_total[cat] = cat_total.get(cat, 0) + 1
        if row["status"] in ("SENT", "PENDING_SEND"):
            cat_sent[cat] = cat_sent.get(cat, 0) + 1

    categories = sorted(
        [
            {
                "label": cat,
                "count": cat_total[cat],
                "sent":  cat_sent.get(cat, 0),
                "color": COLORS[i % len(COLORS)],
            }
            for i, cat in enumerate(cat_total)
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:6]

    # ── 城市分布 ─────────────────────────────────────────────────
    loc_rows = (await session.execute(text(f"""
        SELECT location, COUNT(*) AS cnt
        FROM job
        {job_where + " AND" if job_where else "WHERE"} location IS NOT NULL AND location != ''
        GROUP BY location ORDER BY cnt DESC LIMIT 6
    """))).mappings().all()
    locations = [{"city": r["location"], "count": int(r["cnt"])} for r in loc_rows]

    # ── 评分分布 ─────────────────────────────────────────────────
    score_rows = (await session.execute(text(f"""
        SELECT
            SUM(score < 30)                       AS s0,
            SUM(score >= 30 AND score < 50)       AS s30,
            SUM(score >= 50 AND score < 75)       AS s50,
            SUM(score >= 75)                       AS s75
        FROM job {job_where} {'AND' if job_where else 'WHERE'} score IS NOT NULL AND score > 0
    """))).mappings().first()

    score_dist = [
        {"range": "< 30 (低)",    "count": int(score_rows["s0"]  or 0), "color": "#EF4444"},
        {"range": "30–50 (一般)", "count": int(score_rows["s30"] or 0), "color": "var(--amber)"},
        {"range": "50–75 (良好)", "count": int(score_rows["s50"] or 0), "color": "var(--blue)"},
        {"range": "≥ 75 (优质)",  "count": int(score_rows["s75"] or 0), "color": "var(--green)"},
    ]

    # ── 智能洞察（基于真实数据动态生成）────────────────────────
    insights = []

    top_city = locations[0]["city"] if locations else None
    if top_city:
        insights.append({
            "emoji": "📍",
            "title": "热门城市",
            "desc":  f"抓取岗位最多的城市为「{top_city}」，共 {locations[0]['count']} 条",
        })

    if avg_score > 0:
        insights.append({
            "emoji": "🎯",
            "title": "平均匹配分",
            "desc":  f"当前周期内岗位平均 AI 匹配分为 {avg_score} 分",
        })

    high_score_cnt = score_dist[3]["count"]
    if high_score_cnt:
        insights.append({
            "emoji": "🚀",
            "title": "优质岗位",
            "desc":  f"共 {high_score_cnt} 个岗位匹配分 ≥ 75，建议优先投递",
        })

    if pending > 0:
        insights.append({
            "emoji": "⏳",
            "title": "待处理岗位",
            "desc":  f"还有 {pending} 个岗位等待 AI 评分处理",
        })

    if not insights:
        insights.append({
            "emoji": "💡",
            "title": "暂无数据",
            "desc":  "开始抓取岗位后，这里将展示真实的投递洞察",
        })

    return {
        "summary": {
            "total_scraped": total_scraped,
            "total_sent":    total_sent,
            "total_skipped": total_skipped,
            "pending":       pending,
            "matched":       matched,
            "avg_score":     avg_score,
        },
        "daily":      daily,
        "categories": categories,
        "locations":  locations,
        "score_dist": score_dist,
        "insights":   insights,
    }
