from radar.env import load_dotenv


def test_loads_plain_pairs(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=one\nB=two\n")
    environ: dict[str, str] = {}
    loaded = load_dotenv(path, environ)
    assert environ == {"A": "one", "B": "two"}
    assert loaded == ["A", "B"]


def test_missing_file_is_not_an_error(tmp_path):
    environ: dict[str, str] = {}
    assert load_dotenv(tmp_path / "absent.env", environ) == []
    assert environ == {}


def test_ignores_comments_and_blank_lines(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# a comment\n\nA=1\n   # indented comment\n")
    environ: dict[str, str] = {}
    load_dotenv(path, environ)
    assert environ == {"A": "1"}


def test_strips_quotes_export_and_spaces(tmp_path):
    path = tmp_path / ".env"
    path.write_text('export A = "one two"\nB=\'three\'\nC= four \n')
    environ: dict[str, str] = {}
    load_dotenv(path, environ)
    assert environ == {"A": "one two", "B": "three", "C": "four"}


def test_keeps_equals_signs_inside_values(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=https://example.com/hook?token=abc=\n")
    environ: dict[str, str] = {}
    load_dotenv(path, environ)
    assert environ["A"] == "https://example.com/hook?token=abc="


def test_existing_environment_wins(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=from-file\nB=from-file\n")
    environ = {"A": "from-shell"}
    loaded = load_dotenv(path, environ)
    assert environ == {"A": "from-shell", "B": "from-file"}
    assert loaded == ["B"]


def test_empty_values_are_skipped(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=\nB=\"\"\nC=1\n")
    environ: dict[str, str] = {}
    load_dotenv(path, environ)
    assert environ == {"C": "1"}


def test_malformed_lines_are_skipped(tmp_path):
    path = tmp_path / ".env"
    path.write_text("no equals sign\n=novalue\nA=1\n")
    environ: dict[str, str] = {}
    load_dotenv(path, environ)
    assert environ == {"A": "1"}
