from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from django import template
from django.templatetags.static import static


register = template.Library()


LOCAL_COVER_IMAGES = [
    "anime.jpg",
    "art.jpg",
    "biology.jpg",
    "bookshelf.jpg",
    "comics.jpg",
    "computer.jpg",
    "english.jpg",
    "etica.jpg",
    "fantasy-1.jpg",
    "fantasy-10.jpg",
    "fantasy-2.jpg",
    "fantasy-3.jpg",
    "fantasy-4.jpg",
    "fantasy-5.jpg",
    "fantasy-6.jpg",
    "fantasy-7.jpg",
    "fantasy-8.jpg",
    "fantasy-9.jpg",
    "fantazy_hary_poter.jpg",
    "filosofia.jpg",
    "Fisica.jpg",
    "Geografia.jpg",
    "Historia.jpg",
    "kids.jpg",
    "love-1.jpg",
    "love-2.jpg",
    "love-3.jpg",
    "love-4.jpg",
    "love-5.jpg",
    "love-6.jpg",
    "love-7.jpg",
    "Matematica.jpg",
    "space.jpg",
    "Vintage Books.jpg",
]

DEMO_ISBN_TO_COVER = {
    f"97800000{index:05d}": filename
    for index, filename in enumerate(LOCAL_COVER_IMAGES, start=1)
}
DEMO_ISBN_TO_COVER["9780000000002"] = "fantasy-7.jpg"


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@register.simple_tag
def book_cover(book) -> str:
    if not book:
        return static("books/img/bookicon.png")

    cover_image = getattr(book, "cover_image", None)

    if cover_image:
        try:
            return cover_image.url
        except ValueError:
            pass

    cover_url = (getattr(book, "cover_url", "") or "").strip()

    if _is_http_url(cover_url):
        return cover_url

    isbn13 = (getattr(book, "isbn13", "") or "").strip()
    mapped_cover = DEMO_ISBN_TO_COVER.get(isbn13)

    if mapped_cover:
        return static(f"books/img/{mapped_cover}")

    title = getattr(book, "title", "") or ""
    stable_key = f"{getattr(book, 'pk', '')}:{isbn13}:{title}".encode("utf-8")
    digest = hashlib.blake2s(stable_key, digest_size=4).hexdigest()
    image_index = int(digest, 16) % len(LOCAL_COVER_IMAGES)

    return static(f"books/img/{LOCAL_COVER_IMAGES[image_index]}")
