"""
services.py — бізнес-логіка книжкового застосунку.

Форми відповідають за:
- відображення полів;
- первинну валідацію введення.

Сервіси відповідають за:
- створення, оновлення та видалення об'єктів;
- транзакції;
- перевірку власника даних;
- синхронізацію M2M-зв'язків;
- прогрес і статус читання.

Приклад використання у view:

    if form.is_valid():
        entry = create_library_entry(
            user=request.user,
            **form.cleaned_data,
        )
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    Author,
    Book,
    BookNote,
    Bookmark,
    Category,
    LibraryEntry,
    PersonalTag,
    Quote,
    ReadingSession,
    Review,
    Shelf,
    UserProfile,
)


# =============================================================================
# ДОПОМІЖНІ ФУНКЦІЇ
# =============================================================================

def _object_ids(values: Iterable[Any] | None) -> set[int]:
    """
    Перетворює queryset, список моделей або список ID на множину ID.
    """

    if values is None:
        return set()

    result: set[int] = set()

    for value in values:
        object_id = getattr(value, "pk", value)

        if object_id is not None:
            result.add(int(object_id))

    return result


def _ensure_library_entry_owner(
    library_entry: LibraryEntry,
    user,
) -> None:
    """
    Забороняє працювати із записом бібліотеки іншого користувача.
    """

    if library_entry.user_id != user.id:
        raise PermissionDenied(
            "Ви не маєте доступу до цієї книги в бібліотеці."
        )


def _ensure_tag_owner(tag: PersonalTag, user) -> None:
    if tag.user_id != user.id:
        raise PermissionDenied(
            "Ви не маєте доступу до цього тегу."
        )


def _ensure_shelf_owner(shelf: Shelf, user) -> None:
    if shelf.user_id != user.id:
        raise PermissionDenied(
            "Ви не маєте доступу до цієї полиці."
        )


def _validate_and_get_tags(
    *,
    user,
    tags: Iterable[PersonalTag | int] | None,
):
    """
    Повертає лише теги поточного користувача.

    Якщо серед переданих ID є чужий або неіснуючий тег,
    піднімається ValidationError замість тихого ігнорування.
    """

    tag_ids = _object_ids(tags)

    if not tag_ids:
        return PersonalTag.objects.none()

    valid_tags = PersonalTag.objects.filter(
        user=user,
        pk__in=tag_ids,
    )
    valid_ids = set(
        valid_tags.values_list("pk", flat=True)
    )

    if valid_ids != tag_ids:
        raise ValidationError(
            {
                "tags": (
                    "Один або кілька тегів не існують "
                    "або належать іншому користувачу."
                )
            }
        )

    return valid_tags


def _validate_and_get_library_entries(
    *,
    user,
    entries: Iterable[LibraryEntry | int] | None,
):
    """
    Перевіряє, що всі книги для полиці належать поточному користувачу.
    """

    entry_ids = _object_ids(entries)

    if not entry_ids:
        return LibraryEntry.objects.none()

    valid_entries = LibraryEntry.objects.filter(
        user=user,
        pk__in=entry_ids,
    )
    valid_ids = set(
        valid_entries.values_list("pk", flat=True)
    )

    if valid_ids != entry_ids:
        raise ValidationError(
            {
                "books": (
                    "Одна або кілька книг не належать "
                    "вашій особистій бібліотеці."
                )
            }
        )

    return valid_entries


def _datetime_to_local_date(value: datetime | None):
    if value is None:
        return None

    if timezone.is_aware(value):
        return timezone.localtime(value).date()

    return value.date()


def _apply_reading_state(
    entry: LibraryEntry,
    *,
    auto_dates: bool = True,
) -> None:
    """
    Узгоджує статус, сторінку, відсоток і дати читання.
    """

    if (
        entry.book.pages
        and entry.current_page > entry.book.pages
    ):
        raise ValidationError(
            {
                "current_page": (
                    f"У книзі лише {entry.book.pages} сторінок."
                )
            }
        )

    today = timezone.localdate()

    if (
        entry.status == LibraryEntry.ReadingStatus.READING
        and entry.started_at is None
        and auto_dates
    ):
        entry.started_at = today

    if entry.status == LibraryEntry.ReadingStatus.COMPLETED:
        entry.progress_percent = 100

        if entry.book.pages:
            entry.current_page = entry.book.pages

        if entry.finished_at is None and auto_dates:
            entry.finished_at = today
    else:
        entry.update_progress_from_page()

    if (
        entry.started_at
        and entry.finished_at
        and entry.finished_at < entry.started_at
    ):
        raise ValidationError(
            {
                "finished_at": (
                    "Дата завершення не може бути "
                    "раніше дати початку."
                )
            }
        )


def _validate_page_for_entry(
    *,
    library_entry: LibraryEntry,
    page: int | None,
    field_name: str = "page",
) -> None:
    """Перевіряє сторінку відносно обсягу вибраної книги."""

    if (
        page is not None
        and library_entry.book.pages
        and page > library_entry.book.pages
    ):
        raise ValidationError(
            {
                field_name: (
                    f"У книзі лише {library_entry.book.pages} сторінок."
                )
            }
        )


def _update_entry_from_reading_session(
    entry: LibraryEntry,
    session: ReadingSession,
) -> None:
    """
    Після збереження сесії читання оновлює стан книги.

    Правила:
    - перша сесія переводить WANT_TO_READ у READING;
    - кінцева сторінка оновлює current_page;
    - остання сторінка завершує книгу.
    """

    changed = False

    if entry.status == LibraryEntry.ReadingStatus.WANT_TO_READ:
        entry.status = LibraryEntry.ReadingStatus.READING
        changed = True

    session_start_date = _datetime_to_local_date(
        session.started_at
    )

    if entry.started_at is None and session_start_date is not None:
        entry.started_at = session_start_date
        changed = True

    if (
        session.end_page is not None
        and session.end_page > entry.current_page
    ):
        entry.current_page = session.end_page
        changed = True

    if changed:
        if (
            entry.book.pages
            and entry.current_page >= entry.book.pages
        ):
            entry.status = LibraryEntry.ReadingStatus.COMPLETED
            entry.finished_at = (
                _datetime_to_local_date(session.finished_at)
                or timezone.localdate()
            )

        _apply_reading_state(entry)
        entry.full_clean()
        entry.save(
            update_fields=[
                "status",
                "started_at",
                "finished_at",
                "current_page",
                "progress_percent",
                "updated_at",
            ]
        )


# =============================================================================
# ПРОФІЛЬ КОРИСТУВАЧА
# =============================================================================

@transaction.atomic
def create_or_update_user_profile(
    *,
    user,
    display_name: str = "",
    avatar_url: str = "",
    timezone: str = "UTC",
    bio: str = "",
) -> UserProfile:
    profile, _ = UserProfile.objects.select_for_update().get_or_create(
        user=user
    )

    profile.display_name = display_name
    profile.avatar_url = avatar_url
    profile.timezone = timezone
    profile.bio = bio
    profile.full_clean()
    profile.save()

    return profile


def delete_user_profile(*, profile: UserProfile, user) -> None:
    if profile.user_id != user.id:
        raise PermissionDenied(
            "Ви не можете видалити чужий профіль."
        )

    profile.delete()


# =============================================================================
# АВТОРИ
# =============================================================================

def create_author(
    *,
    name: str,
    biography: str = "",
    website: str = "",
) -> Author:
    author = Author(
        name=name.strip(),
        biography=biography,
        website=website,
    )
    author.full_clean()
    author.save()

    return author


def update_author(
    author: Author,
    *,
    name: str,
    biography: str = "",
    website: str = "",
) -> Author:
    author.name = name.strip()
    author.biography = biography
    author.website = website
    author.full_clean()
    author.save(
        update_fields=[
            "name",
            "biography",
            "website",
            "updated_at",
        ]
    )

    return author


def delete_author(author: Author) -> None:
    author.delete()


# =============================================================================
# КАТЕГОРІЇ
# =============================================================================

def create_category(
    *,
    name: str,
    parent: Category | None = None,
    description: str = "",
) -> Category:
    category = Category(
        name=name.strip(),
        parent=parent,
        description=description,
    )
    category.full_clean()
    category.save()

    return category


def update_category(
    category: Category,
    *,
    name: str,
    parent: Category | None = None,
    description: str = "",
) -> Category:
    if parent is not None:
        current = parent

        while current is not None:
            if current.pk == category.pk:
                raise ValidationError(
                    {
                        "parent": (
                            "Категорія не може бути вкладена "
                            "сама в себе або у власну дочірню категорію."
                        )
                    }
                )

            current = current.parent

    category.name = name.strip()
    category.parent = parent
    category.description = description
    category.full_clean()
    category.save(
        update_fields=[
            "name",
            "parent",
            "description",
            "updated_at",
        ]
    )

    return category


def delete_category(category: Category) -> None:
    category.delete()


# =============================================================================
# КНИГИ
# =============================================================================

@transaction.atomic
def create_book(
    *,
    added_by,
    title: str,
    authors,
    subtitle: str = "",
    categories=None,
    isbn13: str | None = None,
    publisher: str = "",
    published_year: int | None = None,
    pages: int | None = None,
    language: str = "",
    description: str = "",
    cover_url: str = "",
    series_name: str = "",
    series_number=None,
) -> Book:
    book = Book(
        added_by=added_by,
        title=title.strip(),
        subtitle=subtitle,
        isbn13=isbn13 or None,
        publisher=publisher,
        published_year=published_year,
        pages=pages,
        language=language,
        description=description,
        cover_url=cover_url,
        series_name=series_name,
        series_number=series_number,
    )
    book.full_clean()
    book.save()

    book.authors.set(authors)
    book.categories.set(categories or [])

    return book


@transaction.atomic
def update_book(
    book: Book,
    *,
    title: str,
    authors,
    subtitle: str = "",
    categories=None,
    isbn13: str | None = None,
    publisher: str = "",
    published_year: int | None = None,
    pages: int | None = None,
    language: str = "",
    description: str = "",
    cover_url: str = "",
    series_name: str = "",
    series_number=None,
) -> Book:
    locked_book = Book.objects.select_for_update().get(pk=book.pk)

    locked_book.title = title.strip()
    locked_book.subtitle = subtitle
    locked_book.isbn13 = isbn13 or None
    locked_book.publisher = publisher
    locked_book.published_year = published_year
    locked_book.pages = pages
    locked_book.language = language
    locked_book.description = description
    locked_book.cover_url = cover_url
    locked_book.series_name = series_name
    locked_book.series_number = series_number

    locked_book.full_clean()
    locked_book.save()

    locked_book.authors.set(authors)
    locked_book.categories.set(categories or [])

    return locked_book


def delete_book(book: Book) -> None:
    book.delete()


# =============================================================================
# ОСОБИСТІ ТЕГИ
# =============================================================================

def create_personal_tag(
    *,
    user,
    name: str,
    color: str = "#3498db",
) -> PersonalTag:
    normalized_name = name.strip()

    if PersonalTag.objects.filter(
        user=user,
        name__iexact=normalized_name,
    ).exists():
        raise ValidationError(
            {"name": "У вас уже є тег із такою назвою."}
        )

    tag = PersonalTag(
        user=user,
        name=normalized_name,
        color=color,
    )
    tag.full_clean()
    tag.save()

    return tag


def update_personal_tag(
    tag: PersonalTag,
    *,
    user,
    name: str,
    color: str = "#3498db",
) -> PersonalTag:
    _ensure_tag_owner(tag, user)

    normalized_name = name.strip()

    duplicate_exists = PersonalTag.objects.filter(
        user=user,
        name__iexact=normalized_name,
    ).exclude(pk=tag.pk).exists()

    if duplicate_exists:
        raise ValidationError(
            {"name": "У вас уже є тег із такою назвою."}
        )

    tag.name = normalized_name
    tag.color = color
    tag.full_clean()
    tag.save(
        update_fields=[
            "name",
            "color",
            "updated_at",
        ]
    )

    return tag


def delete_personal_tag(
    tag: PersonalTag,
    *,
    user,
) -> None:
    _ensure_tag_owner(tag, user)
    tag.delete()


# =============================================================================
# ОСОБИСТА БІБЛІОТЕКА
# =============================================================================

@transaction.atomic
def create_library_entry(
    *,
    user,
    book: Book,
    status: str = LibraryEntry.ReadingStatus.WANT_TO_READ,
    book_format: str = LibraryEntry.BookFormat.PAPER,
    visibility: str = LibraryEntry.Visibility.PRIVATE,
    current_page: int = 0,
    rating: int | None = None,
    is_favorite: bool = False,
    is_owned: bool = True,
    started_at=None,
    finished_at=None,
    tags=None,
) -> LibraryEntry:
    if LibraryEntry.objects.filter(
        user=user,
        book=book,
    ).exists():
        raise ValidationError(
            {"book": "Ця книга вже є у вашій бібліотеці."}
        )

    entry = LibraryEntry(
        user=user,
        book=book,
        status=status,
        book_format=book_format,
        visibility=visibility,
        current_page=current_page,
        rating=rating,
        is_favorite=is_favorite,
        is_owned=is_owned,
        started_at=started_at,
        finished_at=finished_at,
    )

    _apply_reading_state(entry)
    entry.full_clean()
    entry.save()

    valid_tags = _validate_and_get_tags(
        user=user,
        tags=tags,
    )
    entry.tags.set(valid_tags)

    return entry


@transaction.atomic
def update_library_entry(
    entry: LibraryEntry,
    *,
    user,
    book: Book,
    status: str,
    book_format: str,
    visibility: str,
    current_page: int = 0,
    rating: int | None = None,
    is_favorite: bool = False,
    is_owned: bool = True,
    started_at=None,
    finished_at=None,
    tags=None,
) -> LibraryEntry:
    locked_entry = (
        LibraryEntry.objects
        .select_for_update()
        .select_related("book")
        .get(pk=entry.pk)
    )
    _ensure_library_entry_owner(locked_entry, user)

    duplicate_exists = LibraryEntry.objects.filter(
        user=user,
        book=book,
    ).exclude(pk=locked_entry.pk).exists()

    if duplicate_exists:
        raise ValidationError(
            {"book": "Ця книга вже є у вашій бібліотеці."}
        )

    locked_entry.book = book
    locked_entry.status = status
    locked_entry.book_format = book_format
    locked_entry.visibility = visibility
    locked_entry.current_page = current_page
    locked_entry.rating = rating
    locked_entry.is_favorite = is_favorite
    locked_entry.is_owned = is_owned
    locked_entry.started_at = started_at
    locked_entry.finished_at = finished_at

    _apply_reading_state(locked_entry)
    locked_entry.full_clean()
    locked_entry.save()

    valid_tags = _validate_and_get_tags(
        user=user,
        tags=tags,
    )
    locked_entry.tags.set(valid_tags)

    return locked_entry


def delete_library_entry(
    entry: LibraryEntry,
    *,
    user,
) -> None:
    _ensure_library_entry_owner(entry, user)
    entry.delete()


@transaction.atomic
def set_reading_progress(
    entry: LibraryEntry,
    *,
    user,
    current_page: int,
) -> LibraryEntry:
    locked_entry = (
        LibraryEntry.objects
        .select_for_update()
        .select_related("book")
        .get(pk=entry.pk)
    )
    _ensure_library_entry_owner(locked_entry, user)

    locked_entry.current_page = current_page

    if (
        locked_entry.book.pages
        and current_page >= locked_entry.book.pages
    ):
        locked_entry.status = LibraryEntry.ReadingStatus.COMPLETED
    elif locked_entry.status == LibraryEntry.ReadingStatus.WANT_TO_READ:
        locked_entry.status = LibraryEntry.ReadingStatus.READING

    _apply_reading_state(locked_entry)
    locked_entry.full_clean()
    locked_entry.save()

    return locked_entry


@transaction.atomic
def mark_book_as_completed(
    entry: LibraryEntry,
    *,
    user,
    finished_at=None,
) -> LibraryEntry:
    locked_entry = (
        LibraryEntry.objects
        .select_for_update()
        .select_related("book")
        .get(pk=entry.pk)
    )
    _ensure_library_entry_owner(locked_entry, user)

    locked_entry.status = LibraryEntry.ReadingStatus.COMPLETED
    locked_entry.finished_at = (
        finished_at or timezone.localdate()
    )

    _apply_reading_state(locked_entry)
    locked_entry.full_clean()
    locked_entry.save()

    return locked_entry


def toggle_library_favorite(
    entry: LibraryEntry,
    *,
    user,
) -> LibraryEntry:
    _ensure_library_entry_owner(entry, user)

    LibraryEntry.objects.filter(
        pk=entry.pk,
        user=user,
    ).update(is_favorite=~F("is_favorite"))

    entry.refresh_from_db(
        fields=["is_favorite", "updated_at"]
    )

    return entry


# =============================================================================
# ПОЛИЦІ
# =============================================================================

@transaction.atomic
def create_shelf(
    *,
    user,
    name: str,
    description: str = "",
    is_public: bool = False,
    books=None,
) -> Shelf:
    normalized_name = name.strip()

    if Shelf.objects.filter(
        user=user,
        name__iexact=normalized_name,
    ).exists():
        raise ValidationError(
            {"name": "У вас уже є полиця з такою назвою."}
        )

    shelf = Shelf(
        user=user,
        name=normalized_name,
        description=description,
        is_public=is_public,
    )
    shelf.full_clean()
    shelf.save()

    valid_entries = _validate_and_get_library_entries(
        user=user,
        entries=books,
    )
    shelf.books.set(valid_entries)

    return shelf


@transaction.atomic
def update_shelf(
    shelf: Shelf,
    *,
    user,
    name: str,
    description: str = "",
    is_public: bool = False,
    books=None,
) -> Shelf:
    locked_shelf = (
        Shelf.objects
        .select_for_update()
        .get(pk=shelf.pk)
    )
    _ensure_shelf_owner(locked_shelf, user)

    normalized_name = name.strip()

    duplicate_exists = Shelf.objects.filter(
        user=user,
        name__iexact=normalized_name,
    ).exclude(pk=locked_shelf.pk).exists()

    if duplicate_exists:
        raise ValidationError(
            {"name": "У вас уже є полиця з такою назвою."}
        )

    locked_shelf.name = normalized_name
    locked_shelf.description = description
    locked_shelf.is_public = is_public
    locked_shelf.full_clean()
    locked_shelf.save()

    valid_entries = _validate_and_get_library_entries(
        user=user,
        entries=books,
    )
    locked_shelf.books.set(valid_entries)

    return locked_shelf


def delete_shelf(
    shelf: Shelf,
    *,
    user,
) -> None:
    _ensure_shelf_owner(shelf, user)
    shelf.delete()


def add_book_to_shelf(
    shelf: Shelf,
    *,
    user,
    entry: LibraryEntry,
) -> Shelf:
    _ensure_shelf_owner(shelf, user)
    _ensure_library_entry_owner(entry, user)

    shelf.books.add(entry)
    return shelf


def remove_book_from_shelf(
    shelf: Shelf,
    *,
    user,
    entry: LibraryEntry,
) -> Shelf:
    _ensure_shelf_owner(shelf, user)
    _ensure_library_entry_owner(entry, user)

    shelf.books.remove(entry)
    return shelf


# =============================================================================
# НОТАТКИ
# =============================================================================

def create_book_note(
    *,
    user,
    library_entry: LibraryEntry,
    note_type: str = BookNote.NoteType.NOTE,
    title: str = "",
    body: str,
    page: int | None = None,
    is_pinned: bool = False,
) -> BookNote:
    _ensure_library_entry_owner(library_entry, user)
    _validate_page_for_entry(
        library_entry=library_entry,
        page=page,
    )

    note = BookNote(
        library_entry=library_entry,
        note_type=note_type,
        title=title,
        body=body,
        page=page,
        is_pinned=is_pinned,
    )
    note.full_clean()
    note.save()

    return note


def update_book_note(
    note: BookNote,
    *,
    user,
    library_entry: LibraryEntry,
    note_type: str,
    title: str = "",
    body: str,
    page: int | None = None,
    is_pinned: bool = False,
) -> BookNote:
    _ensure_library_entry_owner(note.library_entry, user)
    _ensure_library_entry_owner(library_entry, user)
    _validate_page_for_entry(
        library_entry=library_entry,
        page=page,
    )

    note.library_entry = library_entry
    note.note_type = note_type
    note.title = title
    note.body = body
    note.page = page
    note.is_pinned = is_pinned
    note.full_clean()
    note.save()

    return note


def delete_book_note(
    note: BookNote,
    *,
    user,
) -> None:
    _ensure_library_entry_owner(note.library_entry, user)
    note.delete()


def toggle_book_note_pin(
    note: BookNote,
    *,
    user,
) -> BookNote:
    _ensure_library_entry_owner(note.library_entry, user)

    BookNote.objects.filter(
        pk=note.pk
    ).update(is_pinned=~F("is_pinned"))

    note.refresh_from_db(
        fields=["is_pinned", "updated_at"]
    )

    return note


# =============================================================================
# ЗАКЛАДКИ
# =============================================================================

def create_bookmark(
    *,
    user,
    library_entry: LibraryEntry,
    page: int | None = None,
    position: str = "",
    label: str = "",
    comment: str = "",
) -> Bookmark:
    _ensure_library_entry_owner(library_entry, user)

    if page is None and not position.strip():
        raise ValidationError(
            "Вкажіть сторінку або позицію."
        )

    _validate_page_for_entry(
        library_entry=library_entry,
        page=page,
    )

    bookmark = Bookmark(
        library_entry=library_entry,
        page=page,
        position=position,
        label=label,
        comment=comment,
    )
    bookmark.full_clean()
    bookmark.save()

    return bookmark


def update_bookmark(
    bookmark: Bookmark,
    *,
    user,
    library_entry: LibraryEntry,
    page: int | None = None,
    position: str = "",
    label: str = "",
    comment: str = "",
) -> Bookmark:
    _ensure_library_entry_owner(bookmark.library_entry, user)
    _ensure_library_entry_owner(library_entry, user)

    if page is None and not position.strip():
        raise ValidationError(
            "Вкажіть сторінку або позицію."
        )

    _validate_page_for_entry(
        library_entry=library_entry,
        page=page,
    )

    bookmark.library_entry = library_entry
    bookmark.page = page
    bookmark.position = position
    bookmark.label = label
    bookmark.comment = comment
    bookmark.full_clean()
    bookmark.save()

    return bookmark


def delete_bookmark(
    bookmark: Bookmark,
    *,
    user,
) -> None:
    _ensure_library_entry_owner(bookmark.library_entry, user)
    bookmark.delete()


# =============================================================================
# ЦИТАТИ
# =============================================================================

def create_quote(
    *,
    user,
    library_entry: LibraryEntry,
    text: str,
    page: int | None = None,
    comment: str = "",
    is_favorite: bool = False,
) -> Quote:
    _ensure_library_entry_owner(library_entry, user)

    _validate_page_for_entry(
        library_entry=library_entry,
        page=page,
    )

    quote = Quote(
        library_entry=library_entry,
        text=text,
        page=page,
        comment=comment,
        is_favorite=is_favorite,
    )
    quote.full_clean()
    quote.save()

    return quote


def update_quote(
    quote: Quote,
    *,
    user,
    library_entry: LibraryEntry,
    text: str,
    page: int | None = None,
    comment: str = "",
    is_favorite: bool = False,
) -> Quote:
    _ensure_library_entry_owner(quote.library_entry, user)
    _ensure_library_entry_owner(library_entry, user)

    _validate_page_for_entry(
        library_entry=library_entry,
        page=page,
    )

    quote.library_entry = library_entry
    quote.text = text
    quote.page = page
    quote.comment = comment
    quote.is_favorite = is_favorite
    quote.full_clean()
    quote.save()

    return quote


def delete_quote(
    quote: Quote,
    *,
    user,
) -> None:
    _ensure_library_entry_owner(quote.library_entry, user)
    quote.delete()


def toggle_quote_favorite(
    quote: Quote,
    *,
    user,
) -> Quote:
    _ensure_library_entry_owner(quote.library_entry, user)

    Quote.objects.filter(
        pk=quote.pk
    ).update(is_favorite=~F("is_favorite"))

    quote.refresh_from_db(
        fields=["is_favorite", "updated_at"]
    )

    return quote


# =============================================================================
# РЕЦЕНЗІЇ
# =============================================================================

def create_review(
    *,
    user,
    library_entry: LibraryEntry,
    title: str = "",
    text: str,
    contains_spoilers: bool = False,
    is_published: bool = False,
) -> Review:
    _ensure_library_entry_owner(library_entry, user)

    if Review.objects.filter(
        library_entry=library_entry
    ).exists():
        raise ValidationError(
            {
                "library_entry": (
                    "Для цієї книги вже створено рецензію."
                )
            }
        )

    review = Review(
        library_entry=library_entry,
        title=title,
        text=text,
        contains_spoilers=contains_spoilers,
        is_published=is_published,
    )
    review.full_clean()
    review.save()

    return review


def update_review(
    review: Review,
    *,
    user,
    library_entry: LibraryEntry,
    title: str = "",
    text: str,
    contains_spoilers: bool = False,
    is_published: bool = False,
) -> Review:
    _ensure_library_entry_owner(review.library_entry, user)
    _ensure_library_entry_owner(library_entry, user)

    duplicate_exists = Review.objects.filter(
        library_entry=library_entry
    ).exclude(pk=review.pk).exists()

    if duplicate_exists:
        raise ValidationError(
            {
                "library_entry": (
                    "Для цієї книги вже створено рецензію."
                )
            }
        )

    review.library_entry = library_entry
    review.title = title
    review.text = text
    review.contains_spoilers = contains_spoilers
    review.is_published = is_published
    review.full_clean()
    review.save()

    return review


def delete_review(
    review: Review,
    *,
    user,
) -> None:
    _ensure_library_entry_owner(review.library_entry, user)
    review.delete()


def toggle_review_publication(
    review: Review,
    *,
    user,
) -> Review:
    _ensure_library_entry_owner(review.library_entry, user)

    Review.objects.filter(
        pk=review.pk
    ).update(is_published=~F("is_published"))

    review.refresh_from_db(
        fields=["is_published", "updated_at"]
    )

    return review


# =============================================================================
# СЕСІЇ ЧИТАННЯ
# =============================================================================

@transaction.atomic
def create_reading_session(
    *,
    user,
    library_entry: LibraryEntry,
    started_at,
    finished_at=None,
    start_page: int | None = None,
    end_page: int | None = None,
    note: str = "",
) -> ReadingSession:
    locked_entry = (
        LibraryEntry.objects
        .select_for_update()
        .select_related("book")
        .get(pk=library_entry.pk)
    )
    _ensure_library_entry_owner(locked_entry, user)

    _validate_page_for_entry(
        library_entry=locked_entry,
        page=start_page,
        field_name="start_page",
    )
    _validate_page_for_entry(
        library_entry=locked_entry,
        page=end_page,
        field_name="end_page",
    )

    session = ReadingSession(
        library_entry=locked_entry,
        started_at=started_at,
        finished_at=finished_at,
        start_page=start_page,
        end_page=end_page,
        note=note,
    )
    session.full_clean()
    session.save()

    _update_entry_from_reading_session(
        locked_entry,
        session,
    )

    return session


@transaction.atomic
def update_reading_session(
    session: ReadingSession,
    *,
    user,
    library_entry: LibraryEntry,
    started_at,
    finished_at=None,
    start_page: int | None = None,
    end_page: int | None = None,
    note: str = "",
) -> ReadingSession:
    old_entry = (
        LibraryEntry.objects
        .select_for_update()
        .select_related("book")
        .get(pk=session.library_entry_id)
    )
    _ensure_library_entry_owner(old_entry, user)

    new_entry = (
        LibraryEntry.objects
        .select_for_update()
        .select_related("book")
        .get(pk=library_entry.pk)
    )
    _ensure_library_entry_owner(new_entry, user)

    _validate_page_for_entry(
        library_entry=new_entry,
        page=start_page,
        field_name="start_page",
    )
    _validate_page_for_entry(
        library_entry=new_entry,
        page=end_page,
        field_name="end_page",
    )

    session.library_entry = new_entry
    session.started_at = started_at
    session.finished_at = finished_at
    session.start_page = start_page
    session.end_page = end_page
    session.note = note
    session.full_clean()
    session.save()

    _update_entry_from_reading_session(
        new_entry,
        session,
    )

    return session


def delete_reading_session(
    session: ReadingSession,
    *,
    user,
) -> None:
    _ensure_library_entry_owner(session.library_entry, user)
    session.delete()
