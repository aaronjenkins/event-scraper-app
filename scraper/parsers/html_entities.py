"""Shared HTML unescape helper for parsers. Uses stdlib html.unescape to
handle the full named + numeric entity set so parsers don't have to ad-hoc
each one (&amp;, &#8217;, &#039;, &quot;, ...)."""
import html


def unescape(text: str) -> str:
    return html.unescape(text)
