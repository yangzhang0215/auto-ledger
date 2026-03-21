from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .schemas import ParseResult

_INCOME_HINTS = ["收入", "收款", "到账", "工资", "奖金", "报销", "转入", "退款", "红包", "收益"]
_EXPENSE_HINTS = ["支出", "花了", "花费", "消费", "付款", "买了", "买", "转出", "扣款", "打车", "吃饭"]

_EXPENSE_CATEGORIES = {
    "餐饮": ["早餐", "午饭", "晚饭", "夜宵", "外卖", "吃饭", "咖啡", "奶茶", "餐饮"],
    "交通": ["打车", "地铁", "公交", "滴滴", "高铁", "火车", "机票", "油费", "停车"],
    "购物": ["淘宝", "京东", "拼多多", "超市", "购物", "衣服", "鞋", "日用品", "买"],
    "住房": ["房租", "租金", "水电", "燃气", "物业", "宽带"],
    "娱乐": ["电影", "游戏", "KTV", "旅游", "演出", "娱乐"],
    "医疗": ["医院", "药", "看病", "体检", "医疗"],
    "教育": ["课程", "学费", "培训", "书", "教育"],
    "通讯": ["话费", "流量", "手机费"],
}

_INCOME_CATEGORIES = {
    "工资": ["工资", "薪资", "salary"],
    "奖金": ["奖金", "绩效", "年终"],
    "报销": ["报销"],
    "退款": ["退款", "返现"],
    "理财": ["利息", "收益", "分红"],
    "其他收入": ["转账", "收款", "红包", "收入"],
}

_FULLWIDTH_TABLE = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "．": ".",
        "，": ",",
        "：": ":",
        "＋": "+",
        "－": "-",
        "￥": "¥",
    }
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().translate(_FULLWIDTH_TABLE))


def _detect_direction(text: str) -> str:
    lowered = text.lower()
    if re.search(r"(^|\s)\+\d", text):
        return "income"
    if re.search(r"(^|\s)-\d", text):
        return "expense"
    if any(k in lowered for k in _INCOME_HINTS):
        return "income"
    if any(k in lowered for k in _EXPENSE_HINTS):
        return "expense"
    return "expense"


def _extract_datetime(text: str, tz_name: str) -> tuple[datetime, str]:
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz=tz).replace(tzinfo=None)
    except ZoneInfoNotFoundError:
        now = datetime.now()
    cleaned = text
    when = now

    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", cleaned)
    if m:
        year, month, day = [int(x) for x in m.groups()]
        when = when.replace(year=year, month=month, day=day)
        cleaned = cleaned.replace(m.group(0), " ", 1)
    else:
        m2 = re.search(r"(\d{1,2})[-/月](\d{1,2})日?", cleaned)
        if m2:
            month, day = [int(x) for x in m2.groups()]
            year = now.year
            candidate = when.replace(year=year, month=month, day=day)
            if candidate > now + timedelta(days=1):
                candidate = candidate.replace(year=year - 1)
            when = candidate
            cleaned = cleaned.replace(m2.group(0), " ", 1)
        elif "昨天" in cleaned:
            when = when - timedelta(days=1)
            cleaned = cleaned.replace("昨天", " ", 1)
        elif "前天" in cleaned:
            when = when - timedelta(days=2)
            cleaned = cleaned.replace("前天", " ", 1)
        elif "今天" in cleaned:
            cleaned = cleaned.replace("今天", " ", 1)

    tm = re.search(r"(\d{1,2}):(\d{1,2})", cleaned)
    if tm:
        hh, mm = [int(x) for x in tm.groups()]
        hh = min(max(hh, 0), 23)
        mm = min(max(mm, 0), 59)
        when = when.replace(hour=hh, minute=mm, second=0, microsecond=0)
        cleaned = cleaned.replace(tm.group(0), " ", 1)

    return when, re.sub(r"\s+", " ", cleaned).strip()


def _extract_amount(text: str) -> tuple[float, str]:
    amount_pattern = re.compile(r"([+-]?\d+(?:\.\d{1,2})?)\s*(?:元|块|块钱|rmb|RMB|¥)?")
    candidates = list(amount_pattern.finditer(text))
    if not candidates:
        raise ValueError("消息中没有识别到金额，示例：`午饭 23` 或 `收入 500 工资`")

    selected = max(candidates, key=lambda m: abs(float(m.group(1))))
    raw_num = selected.group(1)
    amount = abs(float(raw_num))

    cleaned = text[: selected.start()] + " " + text[selected.end() :]
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return amount, cleaned


def _guess_category(direction: str, text: str) -> str:
    lowered = text.lower()
    mapping = _INCOME_CATEGORIES if direction == "income" else _EXPENSE_CATEGORIES
    for category, keywords in mapping.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return category
    return "其他收入" if direction == "income" else "其他"


def parse_text_to_transaction(text: str, tz_name: str = "Asia/Shanghai") -> ParseResult:
    normalized = _normalize(text)
    if not normalized:
        raise ValueError("消息不能为空")

    direction = _detect_direction(normalized)
    occurred_at, without_time = _extract_datetime(normalized, tz_name=tz_name)
    amount, note_candidate = _extract_amount(without_time)
    category = _guess_category(direction, normalized)

    note = note_candidate.strip(" ,-")
    if not note:
        note = normalized

    return ParseResult(
        direction=direction,
        amount=amount,
        category=category,
        note=note[:255],
        occurred_at=occurred_at,
        raw_text=normalized[:1000],
    )
