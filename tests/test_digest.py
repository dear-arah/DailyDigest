from datetime import datetime, timezone

from radar.digest import build_digest

NOW = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)


def record(n, score):
    return {
        "title": f"Story {n}",
        "url": f"https://example.com/{n}",
        "source": "Vendor Blog",
        "tier": 1,
        "score": score,
        "tag": "opportunity",
        "product": "Conversational AI Engine",
        "summary": f"Summary {n}.",
        "angle": f"Angle {n}.",
    }


def test_digest_orders_by_score_and_limits_to_five():
    records = [record(n, score) for n, score in enumerate([3, 9, 5, 7, 6, 8, 4])]

    embed = build_digest(records, NOW)

    assert len(embed["fields"]) == 5
    assert embed["fields"][0]["name"].endswith("Story 1")
    scores = [int(f["value"].split("/10")[0].split()[-1]) for f in embed["fields"]]
    assert scores == [9, 8, 7, 6, 5]


def test_digest_none_when_empty():
    assert build_digest([], NOW) is None


def test_digest_field_has_link_blurb_and_respects_limits():
    long = record(1, 9)
    long["title"] = "t" * 400
    long["summary"] = "s" * 2000

    embed = build_digest([long], NOW)

    field = embed["fields"][0]
    assert len(field["name"]) <= 256
    assert len(field["value"]) <= 1024
    assert "https://example.com/1" in field["value"]


def test_digest_title_has_date():
    embed = build_digest([record(1, 9)], NOW)

    assert "October 28, 2026" in embed["title"]
