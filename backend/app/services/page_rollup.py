"""统计与违规页的数据出口：原样透出最新方案里钉死的结果。

方案生成/改距重排时，排座图、违规、人数已按同一距离算好并存入
result_json；这里不做任何二次加工，保证考室字段、排座图、违规、
人数四处看到的永远是同一份数字。
"""
from __future__ import annotations


def mix_stats(data: dict, stats: dict | None = None) -> dict:
    """返回方案落库时钉死的统计块（seated/unplaced/violations/capacity）。"""
    return dict(stats or data.get("stats") or {})


def mix_violations(data: dict) -> dict:
    """返回方案落库时钉死的违规列表与未排上名单。"""
    return {
        "violations": list(data.get("violations") or []),
        "unplaced": list(data.get("unplaced") or []),
    }
