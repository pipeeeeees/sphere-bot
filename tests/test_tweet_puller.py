from toaster.modules.tweet_puller import _search_for_status_links


def test_search_returns_latest_when_feed_has_no_pinned_tweet():
    html = (
        '<article><a href="/Braves/status/2091713319132422486">latest</a></article>'
        '<article><a href="/Braves/status/2091310980663767267">older</a></article>'
    )

    assert _search_for_status_links(html, "Braves") == (
        "https://x.com/Braves/status/2091713319132422486"
    )


def test_search_skips_status_marked_pinned():
    html = (
        '<article><div>Pinned</div>'
        '<a href="/Braves/status/2088771820757336419">pinned</a></article>'
        '<article><a href="/Braves/status/2091713319132422486">latest</a></article>'
    )

    assert _search_for_status_links(html, "Braves") == (
        "https://x.com/Braves/status/2091713319132422486"
    )


def test_search_skips_pinned_marker_far_before_status_link():
    html = (
        '<div>Pinned</div>'
        + '<span>feed markup</span>' * 70
        + '<article><a href="/Fortnite/status/2090402105031037422">pinned</a></article>'
        + '<article><a href="/Fortnite/status/2092675883190436330">latest</a></article>'
    )

    assert _search_for_status_links(html, "Fortnite") == (
        "https://x.com/Fortnite/status/2092675883190436330"
    )