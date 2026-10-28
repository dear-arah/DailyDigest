from radar.__main__ import main


def write_config(tmp_path):
    (tmp_path / "sources.yaml").write_text(
        "sources:\n  - {name: S, url: 'https://f.example/rss', tier: 1}\n"
    )
    (tmp_path / "context.md").write_text("Agora context.")
    channel = tmp_path / "news.yaml"
    channel.write_text(
        f"""
name: news
webhook_env: DIGEST_TEST_HOOK
sources_file: {tmp_path / "sources.yaml"}
context_file: {tmp_path / "context.md"}
keywords: [voice ai]
threshold: 6
max_posts_per_run: 8
max_age_hours: 48
providers:
  - {{name: gemini, model: m}}
"""
    )
    return channel


def test_run_requires_webhook_unless_dry_run(tmp_path, monkeypatch):
    monkeypatch.delenv("DIGEST_TEST_HOOK", raising=False)
    channel = write_config(tmp_path)

    code = main(["run", "--channel", str(channel), "--state", str(tmp_path / "s.json")])

    assert code == 2


def test_digest_dry_run_with_empty_state_exits_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("DIGEST_TEST_HOOK", raising=False)
    channel = write_config(tmp_path)

    code = main(["digest", "--channel", str(channel), "--state", str(tmp_path / "s.json"), "--dry-run"])

    assert code == 0
    assert "nothing to post" in capsys.readouterr().out.lower()
