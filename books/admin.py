"""
admin.py — адміністративна панель книжкового застосунку.
"""

from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import (
    Author,
    Book,
    BookNote,
    Bookmark,
    Category,
    LibraryEntry,
    LibraryEntryTag,
    PersonalTag,
    Quote,
    ReadingSession,
    Review,
    Shelf,
    ShelfItem,
    UserProfile,
)


admin.site.site_header = "Адміністрування книжкової бібліотеки"
admin.site.site_title = "Книжкова бібліотека"
admin.site.index_title = "Керування даними"


class TimeStampedAdminMixin:
    """Спільні readonly-поля для моделей із часовими мітками."""

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(UserProfile)
class UserProfileAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "user",
        "display_name",
        "timezone",
        "updated_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "display_name",
        "bio",
    )
    list_filter = (
        "timezone",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("user",)
    ordering = ("user__username",)


@admin.register(Author)
class AuthorAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "name",
        "books_count",
        "website",
        "updated_at",
    )
    search_fields = (
        "name",
        "biography",
        "website",
    )
    ordering = ("name",)
    list_per_page = 30

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(_books_count=Count("books", distinct=True))
        )

    @admin.display(
        description="Книг",
        ordering="_books_count",
    )
    def books_count(self, obj):
        return obj._books_count


@admin.register(Category)
class CategoryAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "name",
        "parent",
        "slug",
        "books_count",
        "updated_at",
    )
    list_filter = (
        "parent",
        "created_at",
    )
    search_fields = (
        "name",
        "slug",
        "description",
        "parent__name",
    )
    autocomplete_fields = ("parent",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)
    list_per_page = 30

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("parent")
            .annotate(_books_count=Count("books", distinct=True))
        )

    @admin.display(
        description="Книг",
        ordering="_books_count",
    )
    def books_count(self, obj):
        return obj._books_count


@admin.register(Book)
class BookAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "cover_thumbnail",
        "title",
        "authors_short",
        "published_year",
        "language",
        "isbn13",
        "library_entries_count",
        "added_by",
    )
    list_display_links = (
        "cover_thumbnail",
        "title",
    )
    list_filter = (
        "published_year",
        "language",
        "categories",
        "created_at",
    )
    search_fields = (
        "title",
        "subtitle",
        "authors__name",
        "categories__name",
        "isbn13",
        "publisher",
        "series_name",
        "description",
    )
    filter_horizontal = (
        "authors",
        "categories",
    )
    autocomplete_fields = ("added_by",)
    readonly_fields = (
        "cover_preview",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    ordering = ("title",)
    list_per_page = 25
    save_on_top = True

    fieldsets = (
        (
            "Основна інформація",
            {
                "fields": (
                    "title",
                    "subtitle",
                    "authors",
                    "categories",
                    "description",
                )
            },
        ),
        (
            "Обкладинка",
            {
                "fields": (
                    "cover_image",
                    "cover_url",
                    "cover_preview",
                ),
                "description": (
                    "Завантажений файл має пріоритет над "
                    "зовнішнім посиланням."
                ),
            },
        ),
        (
            "Видання",
            {
                "fields": (
                    "isbn13",
                    "publisher",
                    "published_year",
                    "pages",
                    "language",
                )
            },
        ),
        (
            "Серія",
            {
                "fields": (
                    "series_name",
                    "series_number",
                )
            },
        ),
        (
            "Службова інформація",
            {
                "fields": (
                    "added_by",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("added_by")
            .prefetch_related("authors", "categories")
            .annotate(
                _library_entries_count=Count(
                    "library_entries",
                    distinct=True,
                )
            )
        )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        if obj.added_by_id is None:
            obj.added_by = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )

    @admin.display(description="Обкладинка")
    def cover_thumbnail(self, obj):
        source = obj.cover_source

        if not source:
            return "—"

        return format_html(
            '<img src="{}" alt="" '
            'style="width:44px;height:66px;'
            'object-fit:cover;border-radius:4px;'
            'box-shadow:0 1px 4px rgba(0,0,0,.18);">',
            source,
        )

    @admin.display(description="Попередній перегляд")
    def cover_preview(self, obj):
        source = obj.cover_source

        if not source:
            return "Обкладинку ще не додано."

        return format_html(
            '<img src="{}" alt="Обкладинка {}" '
            'style="max-width:240px;max-height:360px;'
            'object-fit:cover;border-radius:8px;'
            'box-shadow:0 2px 12px rgba(0,0,0,.2);">',
            source,
            obj.title,
        )

    @admin.display(description="Автори")
    def authors_short(self, obj):
        authors = list(obj.authors.all())
        names = ", ".join(author.name for author in authors[:3])

        if len(authors) > 3:
            names += f" та ще {len(authors) - 3}"

        return names or "—"

    @admin.display(
        description="У бібліотеках",
        ordering="_library_entries_count",
    )
    def library_entries_count(self, obj):
        return obj._library_entries_count


@admin.register(PersonalTag)
class PersonalTagAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "name",
        "user",
        "color_preview",
        "entries_count",
        "updated_at",
    )
    list_filter = (
        "user",
        "created_at",
    )
    search_fields = (
        "name",
        "user__username",
        "user__email",
    )
    autocomplete_fields = ("user",)
    ordering = (
        "user__username",
        "name",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .annotate(
                _entries_count=Count(
                    "library_entries",
                    distinct=True,
                )
            )
        )

    @admin.display(description="Колір")
    def color_preview(self, obj):
        color = obj.color or "#cccccc"

        return format_html(
            '<span style="display:inline-block;'
            'width:22px;height:22px;'
            'border-radius:50%;background:{};'
            'border:1px solid #999;"></span> {}',
            color,
            color,
        )

    @admin.display(
        description="Книг",
        ordering="_entries_count",
    )
    def entries_count(self, obj):
        return obj._entries_count


class LibraryEntryTagInline(admin.TabularInline):
    model = LibraryEntryTag
    extra = 0
    autocomplete_fields = ("tag",)
    verbose_name = "Тег"
    verbose_name_plural = "Особисті теги"


@admin.register(LibraryEntry)
class LibraryEntryAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "book",
        "user",
        "status",
        "progress_percent",
        "rating",
        "book_format",
        "visibility",
        "is_favorite",
        "updated_at",
    )
    list_filter = (
        "status",
        "book_format",
        "visibility",
        "is_favorite",
        "is_owned",
        "rating",
        "created_at",
    )
    search_fields = (
        "book__title",
        "book__authors__name",
        "user__username",
        "user__email",
        "tags__name",
    )
    autocomplete_fields = (
        "user",
        "book",
    )
    readonly_fields = (
        "progress_percent",
        "created_at",
        "updated_at",
    )
    inlines = (LibraryEntryTagInline,)
    list_select_related = (
        "user",
        "book",
    )
    ordering = ("-updated_at",)
    list_per_page = 30
    save_on_top = True

    fieldsets = (
        (
            "Книга та користувач",
            {
                "fields": (
                    "user",
                    "book",
                )
            },
        ),
        (
            "Читання",
            {
                "fields": (
                    "status",
                    "book_format",
                    "visibility",
                    "current_page",
                    "progress_percent",
                    "rating",
                    "started_at",
                    "finished_at",
                )
            },
        ),
        (
            "Додатково",
            {
                "fields": (
                    "is_favorite",
                    "is_owned",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        obj.update_progress_from_page()
        obj.full_clean()

        super().save_model(
            request,
            obj,
            form,
            change,
        )


@admin.register(LibraryEntryTag)
class LibraryEntryTagAdmin(admin.ModelAdmin):
    list_display = (
        "library_entry",
        "tag",
    )
    search_fields = (
        "library_entry__book__title",
        "library_entry__user__username",
        "tag__name",
    )
    autocomplete_fields = (
        "library_entry",
        "tag",
    )
    list_select_related = (
        "library_entry",
        "tag",
    )


class ShelfItemInline(admin.TabularInline):
    model = ShelfItem
    extra = 0
    autocomplete_fields = ("library_entry",)
    readonly_fields = ("added_at",)
    verbose_name = "Книга"
    verbose_name_plural = "Книги на полиці"


@admin.register(Shelf)
class ShelfAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "name",
        "user",
        "is_public",
        "books_count",
        "updated_at",
    )
    list_filter = (
        "is_public",
        "user",
        "created_at",
    )
    search_fields = (
        "name",
        "description",
        "user__username",
        "books__book__title",
    )
    autocomplete_fields = ("user",)
    inlines = (ShelfItemInline,)
    ordering = (
        "user__username",
        "name",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .annotate(
                _books_count=Count(
                    "books",
                    distinct=True,
                )
            )
        )

    @admin.display(
        description="Книг",
        ordering="_books_count",
    )
    def books_count(self, obj):
        return obj._books_count


@admin.register(ShelfItem)
class ShelfItemAdmin(admin.ModelAdmin):
    list_display = (
        "shelf",
        "library_entry",
        "added_at",
    )
    list_filter = ("added_at",)
    search_fields = (
        "shelf__name",
        "shelf__user__username",
        "library_entry__book__title",
    )
    autocomplete_fields = (
        "shelf",
        "library_entry",
    )
    readonly_fields = ("added_at",)
    list_select_related = (
        "shelf",
        "library_entry",
        "library_entry__book",
    )


@admin.register(BookNote)
class BookNoteAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "display_title",
        "book_title",
        "user_name",
        "note_type",
        "page",
        "is_pinned",
        "updated_at",
    )
    list_filter = (
        "note_type",
        "is_pinned",
        "created_at",
    )
    search_fields = (
        "title",
        "body",
        "library_entry__book__title",
        "library_entry__user__username",
    )
    autocomplete_fields = ("library_entry",)
    list_select_related = (
        "library_entry",
        "library_entry__book",
        "library_entry__user",
    )
    ordering = (
        "-is_pinned",
        "-updated_at",
    )

    @admin.display(description="Нотатка")
    def display_title(self, obj):
        return obj.title or "Без заголовка"

    @admin.display(description="Книга")
    def book_title(self, obj):
        return obj.library_entry.book.title

    @admin.display(description="Користувач")
    def user_name(self, obj):
        return obj.library_entry.user


@admin.register(Bookmark)
class BookmarkAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "book_title",
        "user_name",
        "label",
        "page",
        "position",
        "updated_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "label",
        "comment",
        "position",
        "library_entry__book__title",
        "library_entry__user__username",
    )
    autocomplete_fields = ("library_entry",)
    list_select_related = (
        "library_entry",
        "library_entry__book",
        "library_entry__user",
    )

    @admin.display(description="Книга")
    def book_title(self, obj):
        return obj.library_entry.book.title

    @admin.display(description="Користувач")
    def user_name(self, obj):
        return obj.library_entry.user


@admin.register(Quote)
class QuoteAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "short_text",
        "book_title",
        "user_name",
        "page",
        "is_favorite",
        "created_at",
    )
    list_filter = (
        "is_favorite",
        "created_at",
    )
    search_fields = (
        "text",
        "comment",
        "library_entry__book__title",
        "library_entry__user__username",
    )
    autocomplete_fields = ("library_entry",)
    list_select_related = (
        "library_entry",
        "library_entry__book",
        "library_entry__user",
    )

    @admin.display(description="Цитата")
    def short_text(self, obj):
        return (
            obj.text[:80] + "…"
            if len(obj.text) > 80
            else obj.text
        )

    @admin.display(description="Книга")
    def book_title(self, obj):
        return obj.library_entry.book.title

    @admin.display(description="Користувач")
    def user_name(self, obj):
        return obj.library_entry.user


@admin.register(Review)
class ReviewAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "book_title",
        "user_name",
        "title",
        "contains_spoilers",
        "is_published",
        "updated_at",
    )
    list_filter = (
        "contains_spoilers",
        "is_published",
        "created_at",
    )
    search_fields = (
        "title",
        "text",
        "library_entry__book__title",
        "library_entry__user__username",
    )
    autocomplete_fields = ("library_entry",)
    list_select_related = (
        "library_entry",
        "library_entry__book",
        "library_entry__user",
    )

    @admin.display(description="Книга")
    def book_title(self, obj):
        return obj.library_entry.book.title

    @admin.display(description="Користувач")
    def user_name(self, obj):
        return obj.library_entry.user


@admin.register(ReadingSession)
class ReadingSessionAdmin(
    TimeStampedAdminMixin,
    admin.ModelAdmin,
):
    list_display = (
        "book_title",
        "user_name",
        "started_at",
        "finished_at",
        "start_page",
        "end_page",
        "pages_read_display",
    )
    list_filter = (
        "started_at",
        "finished_at",
    )
    search_fields = (
        "note",
        "library_entry__book__title",
        "library_entry__user__username",
    )
    autocomplete_fields = ("library_entry",)
    readonly_fields = (
        "pages_read_display",
        "duration_display",
        "created_at",
        "updated_at",
    )
    list_select_related = (
        "library_entry",
        "library_entry__book",
        "library_entry__user",
    )
    date_hierarchy = "started_at"

    @admin.display(description="Книга")
    def book_title(self, obj):
        return obj.library_entry.book.title

    @admin.display(description="Користувач")
    def user_name(self, obj):
        return obj.library_entry.user

    @admin.display(description="Прочитано сторінок")
    def pages_read_display(self, obj):
        return (
            obj.pages_read
            if obj.pages_read is not None
            else "—"
        )

    @admin.display(description="Тривалість")
    def duration_display(self, obj):
        return obj.duration or "—"
