"""
selectors.py — SELECT-запити книжкового застосунку.

У цьому модулі немає INSERT / UPDATE / DELETE.

Selectors відповідають за:
- отримання книг і даних особистої бібліотеки;
- фільтрацію та пошук;
- перевірку доступу до приватних об'єктів через queryset;
- оптимізацію ORM-запитів;
- підготовку статистики для дашборду.

Бізнес-логіка зміни даних знаходиться у services.py.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import (
    Avg,
    Count,
    ExpressionWrapper,
    F,
    IntegerField,
    Prefetch,
    Q,
    Sum,
)
from django.db.models.functions import TruncDate
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
# ДОПОМІЖНІ ФУНКЦІЇ ТА КОНСТАНТИ
# =============================================================================

BOOK_ORDERINGS = {
    "title": "title",
    "-title": "-title",
    "year": "published_year",
    "-year": "-published_year",
    "created": "created_at",
    "-created": "-created_at",
    "popular": "-library_count",
}

LIBRARY_ORDERINGS = {
    "updated": "-updated_at",
    "-updated": "updated_at",
    "title": "book__title",
    "-title": "-book__title",
    "progress": "progress_percent",
    "-progress": "-progress_percent",
    "rating": "rating",
    "-rating": "-rating",
    "started": "started_at",
    "-started": "-started_at",
    "finished": "finished_at",
    "-finished": "-finished_at",
}

NOTE_ORDERINGS = {
    "updated": "-updated_at",
    "-updated": "updated_at",
    "created": "-created_at",
    "-created": "created_at",
    "page": "page",
    "-page": "-page",
}


def _apply_ordering(
    queryset,
    *,
    ordering: str | None,
    allowed: dict[str, str],
    default: str,
):
    """
    Застосовує лише дозволене сортування.

    Це не дозволяє передати довільне ім'я поля з GET-параметра.
    """

    ordering_field = allowed.get(ordering or "", default)
    return queryset.order_by(ordering_field)


def _book_list_queryset():
    """
    Базовий оптимізований queryset каталогу книг.
    """

    return (
        Book.objects
        .prefetch_related("authors", "categories")
        .annotate(
            library_count=Count(
                "library_entries",
                distinct=True,
            ),
            published_reviews_count=Count(
                "library_entries__review",
                filter=Q(
                    library_entries__review__is_published=True,
                    library_entries__visibility=(
                        LibraryEntry.Visibility.PUBLIC
                    ),
                ),
                distinct=True,
            ),
        )
    )


def _library_entry_list_queryset(user):
    """
    Базовий queryset особистої бібліотеки.

    select_related:
        book — ForeignKey, тому отримуємо одним JOIN.

    prefetch_related:
        authors, categories, tags, shelves — M2M-зв'язки,
        тому Django виконує окремі оптимізовані запити.
    """

    return (
        LibraryEntry.objects
        .filter(user=user)
        .select_related("book", "user")
        .prefetch_related(
            "book__authors",
            "book__categories",
            "tags",
            "shelves",
        )
    )


# =============================================================================
# ПРОФІЛЬ
# =============================================================================

def get_user_profile(user) -> UserProfile:
    """
    Повертає профіль поточного користувача.

    Піднімає UserProfile.DoesNotExist, якщо профіль ще не створено.
    """

    return (
        UserProfile.objects
        .select_related("user")
        .get(user=user)
    )


def get_public_profile(user_id: int) -> UserProfile:
    """
    Публічна інформація профілю за ID користувача.
    """

    return (
        UserProfile.objects
        .select_related("user")
        .get(user_id=user_id)
    )


# =============================================================================
# КАТАЛОГ КНИГ
# =============================================================================

def get_books(
    *,
    search: str | None = None,
    category: Category | int | None = None,
    author: Author | int | None = None,
    published_year: int | None = None,
    language: str | None = None,
    ordering: str = "title",
):
    """
    Каталог книг із пошуком, фільтрами та без N+1-запитів.

    search шукає за:
    - назвою;
    - підзаголовком;
    - автором;
    - ISBN;
    - видавництвом;
    - описом.
    """

    queryset = _book_list_queryset()

    if search:
        search = search.strip()

        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(subtitle__icontains=search)
            | Q(authors__name__icontains=search)
            | Q(isbn13__icontains=search)
            | Q(publisher__icontains=search)
            | Q(description__icontains=search)
        )

    if category is not None:
        category_id = getattr(category, "pk", category)
        queryset = queryset.filter(categories__pk=category_id)

    if author is not None:
        author_id = getattr(author, "pk", author)
        queryset = queryset.filter(authors__pk=author_id)

    if published_year is not None:
        queryset = queryset.filter(
            published_year=published_year
        )

    if language:
        queryset = queryset.filter(
            language__iexact=language.strip()
        )

    queryset = queryset.distinct()

    return _apply_ordering(
        queryset,
        ordering=ordering,
        allowed=BOOK_ORDERINGS,
        default="title",
    )


def get_book_detail(book_id: int) -> Book:
    """
    Детальна сторінка книги.

    Додатково завантажує лише опубліковані рецензії,
    власники яких зробили запис бібліотеки публічним.

    У шаблоні:
        book.public_review_entries
    """

    public_review_entries = (
        LibraryEntry.objects
        .filter(
            visibility=LibraryEntry.Visibility.PUBLIC,
            review__is_published=True,
        )
        .select_related("user", "review")
        .order_by("-review__updated_at")
    )

    return (
        _book_list_queryset()
        .prefetch_related(
            Prefetch(
                "library_entries",
                queryset=public_review_entries,
                to_attr="public_review_entries",
            )
        )
        .get(pk=book_id)
    )


def get_book_by_isbn(isbn13: str) -> Book:
    normalized_isbn = (
        isbn13.replace("-", "")
        .replace(" ", "")
        .strip()
    )

    return (
        _book_list_queryset()
        .get(isbn13=normalized_isbn)
    )


def get_books_by_author(
    author: Author | int,
    *,
    ordering: str = "title",
):
    author_id = getattr(author, "pk", author)

    queryset = get_books(
        author=author_id,
        ordering=ordering,
    )

    return queryset


def get_books_by_category(
    category: Category | int,
    *,
    include_children: bool = False,
    ordering: str = "title",
):
    category_id = getattr(category, "pk", category)

    if not include_children:
        return get_books(
            category=category_id,
            ordering=ordering,
        )

    category_ids = Category.objects.filter(
        Q(pk=category_id)
        | Q(parent_id=category_id)
    ).values_list("pk", flat=True)

    queryset = (
        _book_list_queryset()
        .filter(categories__pk__in=category_ids)
        .distinct()
    )

    return _apply_ordering(
        queryset,
        ordering=ordering,
        allowed=BOOK_ORDERINGS,
        default="title",
    )


def get_related_books(
    book: Book,
    *,
    limit: int = 6,
):
    """
    Схожі книги за спільними категоріями.

    shared_categories_count використовується для ранжування.
    """

    category_ids = book.categories.values_list(
        "pk",
        flat=True,
    )

    return (
        _book_list_queryset()
        .filter(categories__pk__in=category_ids)
        .exclude(pk=book.pk)
        .annotate(
            shared_categories_count=Count(
                "categories",
                filter=Q(categories__pk__in=category_ids),
                distinct=True,
            )
        )
        .order_by(
            "-shared_categories_count",
            "-library_count",
            "title",
        )
        .distinct()[:limit]
    )


def get_popular_books(*, limit: int = 10):
    return (
        _book_list_queryset()
        .filter(library_count__gt=0)
        .order_by("-library_count", "title")[:limit]
    )


def get_recent_books(*, limit: int = 10):
    return (
        _book_list_queryset()
        .order_by("-created_at")[:limit]
    )


# =============================================================================
# АВТОРИ
# =============================================================================

def get_authors(
    *,
    search: str | None = None,
):
    queryset = Author.objects.annotate(
        books_count=Count("books", distinct=True)
    )

    if search:
        queryset = queryset.filter(
            name__icontains=search.strip()
        )

    return queryset.order_by("name")


def get_author_detail(author_id: int) -> Author:
    books_queryset = (
        _book_list_queryset()
        .order_by("-published_year", "title")
    )

    return (
        Author.objects
        .annotate(
            books_count=Count("books", distinct=True)
        )
        .prefetch_related(
            Prefetch(
                "books",
                queryset=books_queryset,
                to_attr="ordered_books",
            )
        )
        .get(pk=author_id)
    )


# =============================================================================
# КАТЕГОРІЇ
# =============================================================================

def get_categories(
    *,
    parent: Category | int | None = None,
):
    queryset = Category.objects.annotate(
        books_count=Count("books", distinct=True),
        children_count=Count("children", distinct=True),
    )

    if parent is None:
        queryset = queryset.filter(parent__isnull=True)
    else:
        parent_id = getattr(parent, "pk", parent)
        queryset = queryset.filter(parent_id=parent_id)

    return queryset.order_by("name")


def get_all_categories():
    return (
        Category.objects
        .select_related("parent")
        .annotate(
            books_count=Count("books", distinct=True)
        )
        .order_by("parent__name", "name")
    )


def get_category_tree():
    """
    Повертає кореневі категорії з дочірніми категоріями.

    У шаблоні:
        category.ordered_children
    """

    children_queryset = (
        Category.objects
        .annotate(
            books_count=Count("books", distinct=True)
        )
        .order_by("name")
    )

    return (
        Category.objects
        .filter(parent__isnull=True)
        .annotate(
            books_count=Count("books", distinct=True)
        )
        .prefetch_related(
            Prefetch(
                "children",
                queryset=children_queryset,
                to_attr="ordered_children",
            )
        )
        .order_by("name")
    )


def get_category_detail(category_id: int) -> Category:
    books_queryset = (
        _book_list_queryset()
        .order_by("title")
    )

    return (
        Category.objects
        .select_related("parent")
        .annotate(
            books_count=Count("books", distinct=True),
            children_count=Count("children", distinct=True),
        )
        .prefetch_related(
            "children",
            Prefetch(
                "books",
                queryset=books_queryset,
                to_attr="ordered_books",
            ),
        )
        .get(pk=category_id)
    )


# =============================================================================
# ОСОБИСТА БІБЛІОТЕКА
# =============================================================================

def get_user_library(
    user,
    *,
    status: str | None = None,
    book_format: str | None = None,
    tag: PersonalTag | int | None = None,
    shelf: Shelf | int | None = None,
    favorite: bool | None = None,
    owned: bool | None = None,
    search: str | None = None,
    ordering: str = "updated",
):
    """
    Головний selector особистої бібліотеки.

    Будь-який результат гарантовано належить user.
    """

    queryset = _library_entry_list_queryset(user)

    if status:
        queryset = queryset.filter(status=status)

    if book_format:
        queryset = queryset.filter(
            book_format=book_format
        )

    if tag is not None:
        tag_id = getattr(tag, "pk", tag)
        queryset = queryset.filter(
            tags__pk=tag_id,
            tags__user=user,
        )

    if shelf is not None:
        shelf_id = getattr(shelf, "pk", shelf)
        queryset = queryset.filter(
            shelves__pk=shelf_id,
            shelves__user=user,
        )

    if favorite is not None:
        queryset = queryset.filter(
            is_favorite=favorite
        )

    if owned is not None:
        queryset = queryset.filter(
            is_owned=owned
        )

    if search:
        search = search.strip()

        queryset = queryset.filter(
            Q(book__title__icontains=search)
            | Q(book__subtitle__icontains=search)
            | Q(book__authors__name__icontains=search)
            | Q(book__publisher__icontains=search)
            | Q(book__isbn13__icontains=search)
            | Q(tags__name__icontains=search)
        )

    queryset = queryset.distinct()

    return _apply_ordering(
        queryset,
        ordering=ordering,
        allowed=LIBRARY_ORDERINGS,
        default="-updated_at",
    )


def get_library_entry_detail(
    user,
    entry_id: int,
) -> LibraryEntry:
    """
    Повна сторінка книги в особистій бібліотеці.

    Доступна лише власнику.

    У шаблоні доступні впорядковані списки:
        entry.ordered_notes
        entry.ordered_bookmarks
        entry.ordered_quotes
        entry.ordered_sessions
    """

    notes_queryset = BookNote.objects.order_by(
        "-is_pinned",
        "-updated_at",
    )
    bookmarks_queryset = Bookmark.objects.order_by(
        "page",
        "created_at",
    )
    quotes_queryset = Quote.objects.order_by(
        "-is_favorite",
        "-created_at",
    )
    sessions_queryset = ReadingSession.objects.order_by(
        "-started_at"
    )

    return (
        LibraryEntry.objects
        .filter(user=user)
        .select_related(
            "user",
            "book",
            "review",
        )
        .prefetch_related(
            "book__authors",
            "book__categories",
            "tags",
            "shelves",
            Prefetch(
                "notes",
                queryset=notes_queryset,
                to_attr="ordered_notes",
            ),
            Prefetch(
                "bookmarks",
                queryset=bookmarks_queryset,
                to_attr="ordered_bookmarks",
            ),
            Prefetch(
                "quotes",
                queryset=quotes_queryset,
                to_attr="ordered_quotes",
            ),
            Prefetch(
                "reading_sessions",
                queryset=sessions_queryset,
                to_attr="ordered_sessions",
            ),
        )
        .get(pk=entry_id)
    )


def get_library_entry_by_book(
    user,
    book: Book | int,
) -> LibraryEntry:
    book_id = getattr(book, "pk", book)

    return (
        _library_entry_list_queryset(user)
        .get(book_id=book_id)
    )


def get_currently_reading(
    user,
    *,
    limit: int | None = None,
):
    queryset = get_user_library(
        user,
        status=LibraryEntry.ReadingStatus.READING,
        ordering="-progress",
    )

    if limit is not None:
        return queryset[:limit]

    return queryset


def get_want_to_read(
    user,
    *,
    limit: int | None = None,
):
    queryset = get_user_library(
        user,
        status=LibraryEntry.ReadingStatus.WANT_TO_READ,
        ordering="updated",
    )

    if limit is not None:
        return queryset[:limit]

    return queryset


def get_completed_books(
    user,
    *,
    limit: int | None = None,
):
    queryset = get_user_library(
        user,
        status=LibraryEntry.ReadingStatus.COMPLETED,
        ordering="-finished",
    )

    if limit is not None:
        return queryset[:limit]

    return queryset


def get_favorite_books(
    user,
    *,
    limit: int | None = None,
):
    queryset = get_user_library(
        user,
        favorite=True,
        ordering="-rating",
    )

    if limit is not None:
        return queryset[:limit]

    return queryset


def get_recent_library_entries(
    user,
    *,
    limit: int = 6,
):
    return (
        _library_entry_list_queryset(user)
        .order_by("-created_at")[:limit]
    )


def get_library_stats(user) -> dict:
    """
    Агрегована статистика особистої бібліотеки.

    Один SQL-запит замість окремого count() для кожного статусу.
    """

    stats = LibraryEntry.objects.filter(user=user).aggregate(
        total_books=Count("id"),
        want_to_read=Count(
            "id",
            filter=Q(
                status=LibraryEntry.ReadingStatus.WANT_TO_READ
            ),
        ),
        reading=Count(
            "id",
            filter=Q(
                status=LibraryEntry.ReadingStatus.READING
            ),
        ),
        paused=Count(
            "id",
            filter=Q(
                status=LibraryEntry.ReadingStatus.PAUSED
            ),
        ),
        completed=Count(
            "id",
            filter=Q(
                status=LibraryEntry.ReadingStatus.COMPLETED
            ),
        ),
        dropped=Count(
            "id",
            filter=Q(
                status=LibraryEntry.ReadingStatus.DROPPED
            ),
        ),
        favorites=Count(
            "id",
            filter=Q(is_favorite=True),
        ),
        owned=Count(
            "id",
            filter=Q(is_owned=True),
        ),
        rated_books=Count(
            "id",
            filter=Q(rating__isnull=False),
        ),
        average_rating=Avg(
            "rating",
            filter=Q(rating__isnull=False),
        ),
        current_pages_total=Sum("current_page"),
        completed_pages_total=Sum(
            "book__pages",
            filter=Q(
                status=LibraryEntry.ReadingStatus.COMPLETED
            ),
        ),
    )

    stats["average_rating"] = (
        round(stats["average_rating"], 2)
        if stats["average_rating"] is not None
        else None
    )
    stats["current_pages_total"] = (
        stats["current_pages_total"] or 0
    )
    stats["completed_pages_total"] = (
        stats["completed_pages_total"] or 0
    )

    return stats


def get_library_dashboard(user) -> dict:
    """
    Готові дані для дашборду одним викликом selector layer.
    """

    return {
        "stats": get_library_stats(user),
        "currently_reading": get_currently_reading(
            user,
            limit=5,
        ),
        "recent_books": get_recent_library_entries(
            user,
            limit=6,
        ),
        "favorite_books": get_favorite_books(
            user,
            limit=5,
        ),
        "recent_notes": get_user_notes(
            user,
            ordering="updated",
        )[:5],
        "recent_quotes": get_user_quotes(user)[:5],
    }


# =============================================================================
# ОСОБИСТІ ТЕГИ
# =============================================================================

def get_user_tags(
    user,
    *,
    search: str | None = None,
):
    queryset = (
        PersonalTag.objects
        .filter(user=user)
        .annotate(
            books_count=Count(
                "library_entries",
                distinct=True,
            )
        )
    )

    if search:
        queryset = queryset.filter(
            name__icontains=search.strip()
        )

    return queryset.order_by("name")


def get_user_tag_detail(
    user,
    tag_id: int,
) -> PersonalTag:
    entries_queryset = (
        _library_entry_list_queryset(user)
        .order_by("book__title")
    )

    return (
        PersonalTag.objects
        .filter(user=user)
        .annotate(
            books_count=Count(
                "library_entries",
                distinct=True,
            )
        )
        .prefetch_related(
            Prefetch(
                "library_entries",
                queryset=entries_queryset,
                to_attr="ordered_entries",
            )
        )
        .get(pk=tag_id)
    )


# =============================================================================
# ПОЛИЦІ
# =============================================================================

def get_user_shelves(
    user,
    *,
    search: str | None = None,
):
    queryset = (
        Shelf.objects
        .filter(user=user)
        .annotate(
            books_count=Count("books", distinct=True)
        )
    )

    if search:
        search = search.strip()
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
        )

    return queryset.order_by("name")


def get_shelf_detail(
    user,
    shelf_id: int,
) -> Shelf:
    """
    Приватна сторінка полиці для її власника.

    У шаблоні:
        shelf.ordered_books
    """

    books_queryset = (
        _library_entry_list_queryset(user)
        .order_by("book__title")
    )

    return (
        Shelf.objects
        .filter(user=user)
        .annotate(
            books_count=Count("books", distinct=True)
        )
        .prefetch_related(
            Prefetch(
                "books",
                queryset=books_queryset,
                to_attr="ordered_books",
            )
        )
        .get(pk=shelf_id)
    )


def get_public_shelves(
    *,
    search: str | None = None,
):
    """
    Публічні полиці.

    У public_books потрапляють лише записи бібліотеки
    з visibility=PUBLIC.
    """

    public_books_queryset = (
        LibraryEntry.objects
        .filter(
            visibility=LibraryEntry.Visibility.PUBLIC
        )
        .select_related("book", "user")
        .prefetch_related(
            "book__authors",
            "book__categories",
        )
        .order_by("book__title")
    )

    queryset = (
        Shelf.objects
        .filter(is_public=True)
        .select_related("user")
        .annotate(
            public_books_count=Count(
                "books",
                filter=Q(
                    books__visibility=(
                        LibraryEntry.Visibility.PUBLIC
                    )
                ),
                distinct=True,
            )
        )
        .prefetch_related(
            Prefetch(
                "books",
                queryset=public_books_queryset,
                to_attr="public_books",
            )
        )
    )

    if search:
        search = search.strip()

        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
            | Q(user__username__icontains=search)
        )

    return queryset.order_by("-updated_at")


def get_public_shelf_detail(
    shelf_id: int,
) -> Shelf:
    public_books_queryset = (
        LibraryEntry.objects
        .filter(
            visibility=LibraryEntry.Visibility.PUBLIC
        )
        .select_related("book", "user")
        .prefetch_related(
            "book__authors",
            "book__categories",
        )
        .order_by("book__title")
    )

    return (
        Shelf.objects
        .filter(is_public=True)
        .select_related("user")
        .annotate(
            public_books_count=Count(
                "books",
                filter=Q(
                    books__visibility=(
                        LibraryEntry.Visibility.PUBLIC
                    )
                ),
                distinct=True,
            )
        )
        .prefetch_related(
            Prefetch(
                "books",
                queryset=public_books_queryset,
                to_attr="public_books",
            )
        )
        .get(pk=shelf_id)
    )


# =============================================================================
# НОТАТКИ
# =============================================================================

def get_user_notes(
    user,
    *,
    library_entry: LibraryEntry | int | None = None,
    note_type: str | None = None,
    pinned: bool | None = None,
    search: str | None = None,
    ordering: str = "updated",
):
    queryset = (
        BookNote.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
    )

    if library_entry is not None:
        entry_id = getattr(
            library_entry,
            "pk",
            library_entry,
        )
        queryset = queryset.filter(
            library_entry_id=entry_id
        )

    if note_type:
        queryset = queryset.filter(
            note_type=note_type
        )

    if pinned is not None:
        queryset = queryset.filter(
            is_pinned=pinned
        )

    if search:
        search = search.strip()

        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(body__icontains=search)
            | Q(
                library_entry__book__title__icontains=search
            )
        )

    if ordering == "updated":
        return queryset.order_by(
            "-is_pinned",
            "-updated_at",
        )

    return _apply_ordering(
        queryset,
        ordering=ordering,
        allowed=NOTE_ORDERINGS,
        default="-updated_at",
    )


def get_book_note_detail(
    user,
    note_id: int,
) -> BookNote:
    return (
        BookNote.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
        .get(pk=note_id)
    )


def get_pinned_book_notes(
    user,
    *,
    limit: int = 5,
):
    return (
        get_user_notes(
            user,
            pinned=True,
            ordering="updated",
        )[:limit]
    )


# =============================================================================
# ЗАКЛАДКИ
# =============================================================================

def get_user_bookmarks(
    user,
    *,
    library_entry: LibraryEntry | int | None = None,
    search: str | None = None,
):
    queryset = (
        Bookmark.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
    )

    if library_entry is not None:
        entry_id = getattr(
            library_entry,
            "pk",
            library_entry,
        )
        queryset = queryset.filter(
            library_entry_id=entry_id
        )

    if search:
        search = search.strip()

        queryset = queryset.filter(
            Q(label__icontains=search)
            | Q(comment__icontains=search)
            | Q(position__icontains=search)
            | Q(
                library_entry__book__title__icontains=search
            )
        )

    return queryset.order_by(
        "library_entry__book__title",
        "page",
        "created_at",
    )


def get_bookmark_detail(
    user,
    bookmark_id: int,
) -> Bookmark:
    return (
        Bookmark.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .get(pk=bookmark_id)
    )


# =============================================================================
# ЦИТАТИ
# =============================================================================

def get_user_quotes(
    user,
    *,
    library_entry: LibraryEntry | int | None = None,
    favorite: bool | None = None,
    search: str | None = None,
):
    queryset = (
        Quote.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
    )

    if library_entry is not None:
        entry_id = getattr(
            library_entry,
            "pk",
            library_entry,
        )
        queryset = queryset.filter(
            library_entry_id=entry_id
        )

    if favorite is not None:
        queryset = queryset.filter(
            is_favorite=favorite
        )

    if search:
        search = search.strip()

        queryset = queryset.filter(
            Q(text__icontains=search)
            | Q(comment__icontains=search)
            | Q(
                library_entry__book__title__icontains=search
            )
        )

    return queryset.order_by(
        "-is_favorite",
        "-created_at",
    )


def get_quote_detail(
    user,
    quote_id: int,
) -> Quote:
    return (
        Quote.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .get(pk=quote_id)
    )


def get_favorite_quotes(
    user,
    *,
    limit: int | None = None,
):
    queryset = get_user_quotes(
        user,
        favorite=True,
    )

    if limit is not None:
        return queryset[:limit]

    return queryset


# =============================================================================
# РЕЦЕНЗІЇ
# =============================================================================

def get_user_reviews(
    user,
    *,
    published: bool | None = None,
    search: str | None = None,
):
    queryset = (
        Review.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
    )

    if published is not None:
        queryset = queryset.filter(
            is_published=published
        )

    if search:
        search = search.strip()

        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(text__icontains=search)
            | Q(
                library_entry__book__title__icontains=search
            )
        )

    return queryset.order_by("-updated_at")


def get_review_detail(
    user,
    review_id: int,
) -> Review:
    return (
        Review.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
        .get(pk=review_id)
    )


def get_public_reviews(
    *,
    book: Book | int | None = None,
    search: str | None = None,
):
    """
    Публічні рецензії.

    Потрібні одночасно:
    - Review.is_published=True;
    - LibraryEntry.visibility=PUBLIC.
    """

    queryset = (
        Review.objects
        .filter(
            is_published=True,
            library_entry__visibility=(
                LibraryEntry.Visibility.PUBLIC
            ),
        )
        .select_related(
            "library_entry",
            "library_entry__book",
            "library_entry__user",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
    )

    if book is not None:
        book_id = getattr(book, "pk", book)
        queryset = queryset.filter(
            library_entry__book_id=book_id
        )

    if search:
        search = search.strip()

        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(text__icontains=search)
            | Q(
                library_entry__book__title__icontains=search
            )
            | Q(
                library_entry__user__username__icontains=search
            )
        )

    return queryset.order_by("-updated_at")


def get_public_review_detail(
    review_id: int,
) -> Review:
    return (
        Review.objects
        .filter(
            is_published=True,
            library_entry__visibility=(
                LibraryEntry.Visibility.PUBLIC
            ),
        )
        .select_related(
            "library_entry",
            "library_entry__book",
            "library_entry__user",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
        .get(pk=review_id)
    )


# =============================================================================
# СЕСІЇ ЧИТАННЯ
# =============================================================================

def get_reading_sessions(
    user,
    *,
    library_entry: LibraryEntry | int | None = None,
    date_from=None,
    date_to=None,
):
    queryset = (
        ReadingSession.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .prefetch_related(
            "library_entry__book__authors"
        )
    )

    if library_entry is not None:
        entry_id = getattr(
            library_entry,
            "pk",
            library_entry,
        )
        queryset = queryset.filter(
            library_entry_id=entry_id
        )

    if date_from is not None:
        queryset = queryset.filter(
            started_at__date__gte=date_from
        )

    if date_to is not None:
        queryset = queryset.filter(
            started_at__date__lte=date_to
        )

    return queryset.order_by("-started_at")


def get_reading_session_detail(
    user,
    session_id: int,
) -> ReadingSession:
    return (
        ReadingSession.objects
        .filter(library_entry__user=user)
        .select_related(
            "library_entry",
            "library_entry__book",
        )
        .get(pk=session_id)
    )


def get_recent_reading_sessions(
    user,
    *,
    limit: int = 10,
):
    return get_reading_sessions(user)[:limit]


def get_reading_activity(
    user,
    *,
    days: int = 30,
):
    """
    Статистика читання по днях.

    Результат — queryset словників:

        {
            "day": date,
            "sessions_count": 2,
            "pages_read": 35,
        }
    """

    date_from = timezone.localdate() - timedelta(
        days=max(days - 1, 0)
    )

    page_difference = ExpressionWrapper(
        F("end_page") - F("start_page"),
        output_field=IntegerField(),
    )

    return (
        ReadingSession.objects
        .filter(
            library_entry__user=user,
            started_at__date__gte=date_from,
        )
        .annotate(day=TruncDate("started_at"))
        .values("day")
        .annotate(
            sessions_count=Count("id"),
            pages_read=Sum(
                page_difference,
                filter=Q(
                    start_page__isnull=False,
                    end_page__isnull=False,
                    end_page__gte=F("start_page"),
                ),
            ),
        )
        .order_by("day")
    )


def get_reading_session_stats(
    user,
    *,
    days: int | None = None,
) -> dict:
    queryset = ReadingSession.objects.filter(
        library_entry__user=user
    )

    if days is not None:
        date_from = timezone.now() - timedelta(
            days=days
        )
        queryset = queryset.filter(
            started_at__gte=date_from
        )

    page_difference = ExpressionWrapper(
        F("end_page") - F("start_page"),
        output_field=IntegerField(),
    )

    stats = queryset.aggregate(
        sessions_count=Count("id"),
        pages_read=Sum(
            page_difference,
            filter=Q(
                start_page__isnull=False,
                end_page__isnull=False,
                end_page__gte=F("start_page"),
            ),
        ),
    )

    stats["pages_read"] = stats["pages_read"] or 0

    return stats


# =============================================================================
# QUERYSETS ДЛЯ ФОРМ І SELECT-ПОЛІВ
# =============================================================================

def get_author_choices():
    return Author.objects.order_by("name")


def get_category_choices():
    return (
        Category.objects
        .select_related("parent")
        .order_by("parent__name", "name")
    )


def get_book_choices():
    return (
        Book.objects
        .prefetch_related("authors")
        .order_by("title")
    )


def get_user_tag_choices(user):
    return (
        PersonalTag.objects
        .filter(user=user)
        .order_by("name")
    )


def get_user_library_choices(user):
    return (
        LibraryEntry.objects
        .filter(user=user)
        .select_related("book")
        .prefetch_related("book__authors")
        .order_by("book__title")
    )


def get_user_shelf_choices(user):
    return (
        Shelf.objects
        .filter(user=user)
        .order_by("name")
    )
