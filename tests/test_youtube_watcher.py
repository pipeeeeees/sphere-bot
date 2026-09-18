from toaster.youtube_watcher import _matches_required_title_words


def test_title_filter_matches_required_phrase_case_insensitively():
    assert _matches_required_title_words("Georgia Tech football preview", "Georgia Tech")


def test_title_filter_rejects_titles_without_required_phrase():
    assert not _matches_required_title_words("Atlanta sports update", "Georgia Tech")


def test_title_filter_accepts_any_phrase_in_a_list():
    assert _matches_required_title_words("Georgia Tech football preview", ["Braves", "Georgia Tech"])


def test_title_filter_allows_watches_without_a_requirement():
    assert _matches_required_title_words("Any video", None)