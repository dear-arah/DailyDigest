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


def long_record(n):
    rec = record(n, 9)
    rec["title"] = "t" * 400
    rec["url"] = "https://news.google.com/rss/articles/" + "x" * 330
    rec["summary"] = "s" * 600
    rec["angle"] = "a" * 400
    return rec


def test_digest_cuts_the_blurb_not_the_link():
    rec = long_record(1)

    field = build_digest([rec], NOW)["fields"][0]

    assert field["value"].endswith(f"[Source]({rec['url']})")
    assert len(field["value"]) <= 1000


def test_digest_total_size_stays_under_discord_limit():
    embed = build_digest([long_record(n) for n in range(5)], NOW)

    total = len(embed["title"]) + len(embed["description"])
    total += sum(len(f["name"]) + len(f["value"]) for f in embed["fields"])
    assert total <= 6000


def test_digest_title_has_date():
    embed = build_digest([record(1, 9)], NOW)

    assert "October 28, 2026" in embed["title"]
