"""
views.py — HTTP-рівень книжкового застосунку.

Архітектура:
    forms.py      — відображення та первинна валідація;
    selectors.py  — SELECT-запити;
    services.py   — INSERT / UPDATE / DELETE і бізнес-логіка;
    views.py      — HTTP-запити, повідомлення та перенаправлення.

У цьому файлі навмисно використовуються синхронні Django views.
Не потрібно обгортати звичайний ORM у sync_to_async для такого CRUD-застосунку.
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import selectors, services
from .forms import (
    AuthorForm,
    BookForm,
    BookNoteForm,
    BookmarkForm,
    CategoryForm,
    LibraryEntryForm,
    PersonalTagForm,
    QuoteForm,
    ReadingSessionForm,
    ReviewForm,
    ShelfForm,
    UserProfileForm,
)
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

def _add_service_errors(form, error: ValidationError) -> None:
    """
    Переносить ValidationError із service layer у Django-форму.
    """

    if hasattr(error, "message_dict"):
        for field_name, error_list in error.message_dict.items():
            target_field = field_name

            if (
                field_name == NON_FIELD_ERRORS
                or field_name not in form.fields
            ):
                target_field = None

            for message in error_list:
                form.add_error(target_field, message)

        return

    for message in error.messages:
        form.add_error(None, message)


def _paginate(
    request: HttpRequest,
    queryset,
    *,
    per_page: int = 12,
):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def _optional_int(value: str | None) -> int | None:
    if not value:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: str | None) -> bool | None:
    if value in {"1", "true", "yes"}:
        return True

    if value in {"0", "false", "no"}:
        return False

    return None


def _redirect_to_next(
    request: HttpRequest,
    fallback_name: str,
    **fallback_kwargs,
) -> HttpResponse:
    """
    Безпечно повертає користувача на локальну адресу з POST[next].
    Зовнішні URL ігноруються, щоб не створювати open redirect.
    """

    next_url = request.POST.get("next", "").strip()

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect(
        fallback_name,
        **fallback_kwargs,
    )


def _get_user_entry_or_404(
    user,
    pk: int,
) -> LibraryEntry:
    return get_object_or_404(
        LibraryEntry.objects.select_related("book", "user"),
        pk=pk,
        user=user,
    )


def _user_can_manage_book(user, book: Book) -> bool:
    return bool(
        user.is_staff
        or (
            book.added_by_id is not None
            and book.added_by_id == user.id
        )
    )


def _ensure_user_can_manage_book(user, book: Book) -> None:
    if not _user_can_manage_book(user, book):
        raise Http404("Книгу не знайдено.")


# =============================================================================
# АВТЕНТИФІКАЦІЯ ТА ПРОФІЛЬ
# =============================================================================

def register(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("books:dashboard")

    form = UserCreationForm(
        request.POST or None
    )

    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)

        services.create_or_update_user_profile(
            user=user,
            display_name=user.username,
        )

        messages.success(
            request,
            f"✅ Акаунт «{user.username}» створено.",
        )
        return redirect("books:dashboard")

    return render(
        request,
        "registration/register.html",
        {"form": form},
    )


@login_required
def profile_edit(request: HttpRequest) -> HttpResponse:
    profile = UserProfile.objects.filter(
        user=request.user
    ).first()

    form = UserProfileForm(
        request.POST or None,
        instance=profile,
    )

    if request.method == "POST" and form.is_valid():
        try:
            profile = services.create_or_update_user_profile(
                user=request.user,
                display_name=form.cleaned_data["display_name"],
                avatar_url=form.cleaned_data["avatar_url"],
                timezone=form.cleaned_data["timezone"],
                bio=form.cleaned_data["bio"],
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Профіль оновлено.",
            )
            return redirect(
                "books:profile_edit"
            )

    return render(
        request,
        "books/profile_form.html",
        {
            "form": form,
            "profile": profile,
            "title": "Мій профіль",
        },
    )


def public_profile(
    request: HttpRequest,
    user_id: int,
) -> HttpResponse:
    try:
        profile = selectors.get_public_profile(user_id)
    except UserProfile.DoesNotExist as error:
        raise Http404("Профіль не знайдено.") from error

    public_shelves = selectors.get_public_shelves().filter(
        user_id=user_id
    )
    public_reviews = selectors.get_public_reviews().filter(
        library_entry__user_id=user_id
    )

    return render(
        request,
        "books/public_profile.html",
        {
            "profile": profile,
            "public_shelves": public_shelves,
            "public_reviews": public_reviews,
        },
    )


# =============================================================================
# ДАШБОРД
# =============================================================================

@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    context = selectors.get_library_dashboard(
        request.user
    )
    context["reading_activity"] = (
        selectors.get_reading_activity(
            request.user,
            days=30,
        )
    )
    context["session_stats"] = (
        selectors.get_reading_session_stats(
            request.user,
            days=30,
        )
    )

    return render(
        request,
        "books/dashboard.html",
        context,
    )


# =============================================================================
# КАТАЛОГ КНИГ
# =============================================================================

def book_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    category_id = _optional_int(
        request.GET.get("category")
    )
    author_id = _optional_int(
        request.GET.get("author")
    )
    year = _optional_int(
        request.GET.get("year")
    )
    language = request.GET.get("language", "").strip()
    ordering = request.GET.get("ordering", "title")

    queryset = selectors.get_books(
        search=search or None,
        category=category_id,
        author=author_id,
        published_year=year,
        language=language or None,
        ordering=ordering,
    )

    context = {
        "page_obj": _paginate(
            request,
            queryset,
            per_page=12,
        ),
        "categories": selectors.get_all_categories(),
        "authors": selectors.get_authors(),
        "search": search,
        "active_category_id": category_id,
        "active_author_id": author_id,
        "active_year": year,
        "active_language": language,
        "ordering": ordering,
    }

    return render(
        request,
        "books/book_list.html",
        context,
    )


def book_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        book = selectors.get_book_detail(pk)
    except Book.DoesNotExist as error:
        raise Http404("Книгу не знайдено.") from error

    related_books = selectors.get_related_books(
        book,
        limit=6,
    )

    library_entry = None

    if request.user.is_authenticated:
        try:
            library_entry = (
                selectors.get_library_entry_by_book(
                    request.user,
                    book,
                )
            )
        except LibraryEntry.DoesNotExist:
            pass

    return render(
        request,
        "books/book_detail.html",
        {
            "book": book,
            "related_books": related_books,
            "library_entry": library_entry,
            "can_manage": (
                request.user.is_authenticated
                and _user_can_manage_book(
                    request.user,
                    book,
                )
            ),
        },
    )


@login_required
def book_create(request: HttpRequest) -> HttpResponse:
    form = BookForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            book = services.create_book(
                added_by=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Книгу «{book.title}» додано до каталогу.",
            )
            return redirect(
                "books:book_detail",
                pk=book.pk,
            )

    return render(
        request,
        "books/book_form.html",
        {
            "form": form,
            "title": "Додати книгу",
            "action": "Створити",
        },
    )


@login_required
def book_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    book = get_object_or_404(
        Book.objects.prefetch_related(
            "authors",
            "categories",
        ),
        pk=pk,
    )
    _ensure_user_can_manage_book(
        request.user,
        book,
    )

    form = BookForm(
        request.POST or None,
        instance=book,
    )

    if request.method == "POST" and form.is_valid():
        try:
            book = services.update_book(
                book,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Книгу «{book.title}» оновлено.",
            )
            return redirect(
                "books:book_detail",
                pk=book.pk,
            )

    return render(
        request,
        "books/book_form.html",
        {
            "form": form,
            "book": book,
            "title": f"Редагувати: {book.title}",
            "action": "Зберегти зміни",
        },
    )


@login_required
def book_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    book = get_object_or_404(
        Book,
        pk=pk,
    )
    _ensure_user_can_manage_book(
        request.user,
        book,
    )

    if request.method == "POST":
        title = book.title
        services.delete_book(book)

        messages.warning(
            request,
            f"🗑️ Книгу «{title}» видалено.",
        )
        return redirect("books:book_list")

    return render(
        request,
        "books/book_confirm_delete.html",
        {"book": book},
    )


# =============================================================================
# АВТОРИ
# =============================================================================

def author_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    authors = selectors.get_authors(
        search=search or None
    )

    return render(
        request,
        "books/author_list.html",
        {
            "page_obj": _paginate(
                request,
                authors,
                per_page=20,
            ),
            "search": search,
        },
    )


def author_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        author = selectors.get_author_detail(pk)
    except Author.DoesNotExist as error:
        raise Http404("Автора не знайдено.") from error

    return render(
        request,
        "books/author_detail.html",
        {"author": author},
    )


@login_required
def author_create(request: HttpRequest) -> HttpResponse:
    form = AuthorForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            author = services.create_author(
                **form.cleaned_data
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Автора «{author.name}» створено.",
            )
            return redirect(
                "books:author_detail",
                pk=author.pk,
            )

    return render(
        request,
        "books/author_form.html",
        {
            "form": form,
            "title": "Новий автор",
        },
    )


@staff_member_required
def author_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    author = get_object_or_404(
        Author,
        pk=pk,
    )
    form = AuthorForm(
        request.POST or None,
        instance=author,
    )

    if request.method == "POST" and form.is_valid():
        try:
            author = services.update_author(
                author,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Автора «{author.name}» оновлено.",
            )
            return redirect(
                "books:author_detail",
                pk=author.pk,
            )

    return render(
        request,
        "books/author_form.html",
        {
            "form": form,
            "author": author,
            "title": f"Редагувати: {author.name}",
        },
    )


@staff_member_required
def author_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    author = get_object_or_404(
        Author,
        pk=pk,
    )

    if request.method == "POST":
        name = author.name
        services.delete_author(author)

        messages.warning(
            request,
            f"🗑️ Автора «{name}» видалено.",
        )
        return redirect("books:author_list")

    return render(
        request,
        "books/author_confirm_delete.html",
        {"author": author},
    )


# =============================================================================
# КАТЕГОРІЇ
# =============================================================================

def category_list(
    request: HttpRequest,
) -> HttpResponse:
    return render(
        request,
        "books/category_list.html",
        {
            "categories": selectors.get_category_tree(),
        },
    )


def category_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        category = selectors.get_category_detail(pk)
    except Category.DoesNotExist as error:
        raise Http404("Категорію не знайдено.") from error

    return render(
        request,
        "books/category_detail.html",
        {"category": category},
    )


@login_required
def category_create(
    request: HttpRequest,
) -> HttpResponse:
    form = CategoryForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            category = services.create_category(
                **form.cleaned_data
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Категорію «{category.name}» створено.",
            )
            return redirect(
                "books:category_detail",
                pk=category.pk,
            )

    return render(
        request,
        "books/category_form.html",
        {
            "form": form,
            "title": "Нова категорія",
        },
    )


@staff_member_required
def category_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    category = get_object_or_404(
        Category,
        pk=pk,
    )
    form = CategoryForm(
        request.POST or None,
        instance=category,
    )

    if request.method == "POST" and form.is_valid():
        try:
            category = services.update_category(
                category,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Категорію «{category.name}» оновлено.",
            )
            return redirect(
                "books:category_detail",
                pk=category.pk,
            )

    return render(
        request,
        "books/category_form.html",
        {
            "form": form,
            "category": category,
            "title": f"Редагувати: {category.name}",
        },
    )


@staff_member_required
def category_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    category = get_object_or_404(
        Category,
        pk=pk,
    )

    if request.method == "POST":
        name = category.name
        services.delete_category(category)

        messages.warning(
            request,
            f"🗑️ Категорію «{name}» видалено.",
        )
        return redirect("books:category_list")

    return render(
        request,
        "books/category_confirm_delete.html",
        {"category": category},
    )


# =============================================================================
# ОСОБИСТА БІБЛІОТЕКА
# =============================================================================

@login_required
def library_list(
    request: HttpRequest,
) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status") or None
    book_format = request.GET.get("format") or None
    tag_id = _optional_int(request.GET.get("tag"))
    shelf_id = _optional_int(request.GET.get("shelf"))
    favorite = _optional_bool(
        request.GET.get("favorite")
    )
    owned = _optional_bool(
        request.GET.get("owned")
    )
    ordering = request.GET.get(
        "ordering",
        "updated",
    )

    entries = selectors.get_user_library(
        request.user,
        status=status,
        book_format=book_format,
        tag=tag_id,
        shelf=shelf_id,
        favorite=favorite,
        owned=owned,
        search=search or None,
        ordering=ordering,
    )

    return render(
        request,
        "books/library_list.html",
        {
            "page_obj": _paginate(
                request,
                entries,
                per_page=12,
            ),
            "tags": selectors.get_user_tags(
                request.user
            ),
            "shelves": selectors.get_user_shelves(
                request.user
            ),
            "search": search,
            "active_status": status,
            "active_format": book_format,
            "active_tag_id": tag_id,
            "active_shelf_id": shelf_id,
            "active_favorite": favorite,
            "active_owned": owned,
            "ordering": ordering,
            "reading_statuses": (
                LibraryEntry.ReadingStatus.choices
            ),
            "book_formats": (
                LibraryEntry.BookFormat.choices
            ),
        },
    )


@login_required
def library_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        entry = selectors.get_library_entry_detail(
            request.user,
            pk,
        )
    except LibraryEntry.DoesNotExist as error:
        raise Http404(
            "Книгу у бібліотеці не знайдено."
        ) from error

    return render(
        request,
        "books/library_detail.html",
        {
            "entry": entry,
            "note_form": BookNoteForm(
                user=request.user,
                library_entry=entry,
            ),
            "bookmark_form": BookmarkForm(
                user=request.user,
                library_entry=entry,
            ),
            "quote_form": QuoteForm(
                user=request.user,
                library_entry=entry,
            ),
        },
    )


@login_required
def library_create(
    request: HttpRequest,
    book_id: int | None = None,
) -> HttpResponse:
    selected_book = None

    if book_id is not None:
        selected_book = get_object_or_404(
            Book,
            pk=book_id,
        )

    form = LibraryEntryForm(
        request.POST or None,
        user=request.user,
        book=selected_book,
    )

    if request.method == "POST" and form.is_valid():
        try:
            entry = services.create_library_entry(
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                (
                    f"✅ Книгу «{entry.book.title}» "
                    "додано до вашої бібліотеки."
                ),
            )
            return redirect(
                "books:library_detail",
                pk=entry.pk,
            )

    return render(
        request,
        "books/library_form.html",
        {
            "form": form,
            "selected_book": selected_book,
            "title": "Додати до бібліотеки",
        },
    )


@login_required
def library_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    entry = _get_user_entry_or_404(
        request.user,
        pk,
    )

    form = LibraryEntryForm(
        request.POST or None,
        instance=entry,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            entry = services.update_library_entry(
                entry,
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Дані книги «{entry.book.title}» оновлено.",
            )
            return redirect(
                "books:library_detail",
                pk=entry.pk,
            )

    return render(
        request,
        "books/library_form.html",
        {
            "form": form,
            "entry": entry,
            "title": f"Редагувати: {entry.book.title}",
        },
    )


@login_required
def library_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    entry = _get_user_entry_or_404(
        request.user,
        pk,
    )

    if request.method == "POST":
        title = entry.book.title
        services.delete_library_entry(
            entry,
            user=request.user,
        )

        messages.warning(
            request,
            f"🗑️ Книгу «{title}» вилучено з бібліотеки.",
        )
        return redirect("books:library_list")

    return render(
        request,
        "books/library_confirm_delete.html",
        {"entry": entry},
    )


@login_required
@require_POST
def library_toggle_favorite(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    entry = _get_user_entry_or_404(
        request.user,
        pk,
    )
    entry = services.toggle_library_favorite(
        entry,
        user=request.user,
    )

    message = (
        "⭐ Книгу додано до улюблених."
        if entry.is_favorite
        else "Книгу вилучено з улюблених."
    )
    messages.success(request, message)

    return _redirect_to_next(
        request,
        "books:library_detail",
        pk=entry.pk,
    )


@login_required
@require_POST
def library_mark_completed(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    entry = _get_user_entry_or_404(
        request.user,
        pk,
    )

    try:
        entry = services.mark_book_as_completed(
            entry,
            user=request.user,
        )
    except ValidationError as error:
        messages.error(
            request,
            "; ".join(error.messages),
        )
    else:
        messages.success(
            request,
            f"✅ Книгу «{entry.book.title}» позначено прочитаною.",
        )

    return redirect(
        "books:library_detail",
        pk=entry.pk,
    )


@login_required
@require_POST
def library_set_progress(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    entry = _get_user_entry_or_404(
        request.user,
        pk,
    )

    try:
        current_page = int(
            request.POST.get("current_page", "")
        )
    except (TypeError, ValueError):
        messages.error(
            request,
            "Вкажіть коректний номер сторінки.",
        )
        return redirect(
            "books:library_detail",
            pk=entry.pk,
        )

    try:
        entry = services.set_reading_progress(
            entry,
            user=request.user,
            current_page=current_page,
        )
    except ValidationError as error:
        messages.error(
            request,
            "; ".join(error.messages),
        )
    else:
        messages.success(
            request,
            f"✅ Прогрес оновлено: {entry.progress_percent}%.",
        )

    return redirect(
        "books:library_detail",
        pk=entry.pk,
    )


# =============================================================================
# ОСОБИСТІ ТЕГИ
# =============================================================================

@login_required
def tag_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("search", "").strip()

    return render(
        request,
        "books/tag_list.html",
        {
            "tags": selectors.get_user_tags(
                request.user,
                search=search or None,
            ),
            "search": search,
        },
    )


@login_required
def tag_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        tag = selectors.get_user_tag_detail(
            request.user,
            pk,
        )
    except PersonalTag.DoesNotExist as error:
        raise Http404("Тег не знайдено.") from error

    return render(
        request,
        "books/tag_detail.html",
        {"tag": tag},
    )


@login_required
def tag_create(request: HttpRequest) -> HttpResponse:
    form = PersonalTagForm(
        request.POST or None,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            tag = services.create_personal_tag(
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Тег «{tag.name}» створено.",
            )
            return redirect("books:tag_list")

    return render(
        request,
        "books/tag_form.html",
        {
            "form": form,
            "title": "Новий тег",
        },
    )


@login_required
def tag_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    tag = get_object_or_404(
        PersonalTag,
        pk=pk,
        user=request.user,
    )
    form = PersonalTagForm(
        request.POST or None,
        instance=tag,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            tag = services.update_personal_tag(
                tag,
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Тег «{tag.name}» оновлено.",
            )
            return redirect("books:tag_list")

    return render(
        request,
        "books/tag_form.html",
        {
            "form": form,
            "tag": tag,
            "title": f"Редагувати: {tag.name}",
        },
    )


@login_required
def tag_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    tag = get_object_or_404(
        PersonalTag,
        pk=pk,
        user=request.user,
    )

    if request.method == "POST":
        name = tag.name
        services.delete_personal_tag(
            tag,
            user=request.user,
        )

        messages.warning(
            request,
            f"🗑️ Тег «{name}» видалено.",
        )
        return redirect("books:tag_list")

    return render(
        request,
        "books/tag_confirm_delete.html",
        {"tag": tag},
    )


# =============================================================================
# ПОЛИЦІ
# =============================================================================

@login_required
def shelf_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("search", "").strip()

    return render(
        request,
        "books/shelf_list.html",
        {
            "shelves": selectors.get_user_shelves(
                request.user,
                search=search or None,
            ),
            "search": search,
        },
    )


@login_required
def shelf_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        shelf = selectors.get_shelf_detail(
            request.user,
            pk,
        )
    except Shelf.DoesNotExist as error:
        raise Http404("Полицю не знайдено.") from error

    return render(
        request,
        "books/shelf_detail.html",
        {"shelf": shelf},
    )


@login_required
def shelf_create(request: HttpRequest) -> HttpResponse:
    form = ShelfForm(
        request.POST or None,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            shelf = services.create_shelf(
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Полицю «{shelf.name}» створено.",
            )
            return redirect(
                "books:shelf_detail",
                pk=shelf.pk,
            )

    return render(
        request,
        "books/shelf_form.html",
        {
            "form": form,
            "title": "Нова полиця",
        },
    )


@login_required
def shelf_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    shelf = get_object_or_404(
        Shelf,
        pk=pk,
        user=request.user,
    )
    form = ShelfForm(
        request.POST or None,
        instance=shelf,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            shelf = services.update_shelf(
                shelf,
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                f"✅ Полицю «{shelf.name}» оновлено.",
            )
            return redirect(
                "books:shelf_detail",
                pk=shelf.pk,
            )

    return render(
        request,
        "books/shelf_form.html",
        {
            "form": form,
            "shelf": shelf,
            "title": f"Редагувати: {shelf.name}",
        },
    )


@login_required
def shelf_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    shelf = get_object_or_404(
        Shelf,
        pk=pk,
        user=request.user,
    )

    if request.method == "POST":
        name = shelf.name
        services.delete_shelf(
            shelf,
            user=request.user,
        )

        messages.warning(
            request,
            f"🗑️ Полицю «{name}» видалено.",
        )
        return redirect("books:shelf_list")

    return render(
        request,
        "books/shelf_confirm_delete.html",
        {"shelf": shelf},
    )


@login_required
@require_POST
def shelf_add_book(
    request: HttpRequest,
    pk: int,
    entry_id: int,
) -> HttpResponse:
    shelf = get_object_or_404(
        Shelf,
        pk=pk,
        user=request.user,
    )
    entry = _get_user_entry_or_404(
        request.user,
        entry_id,
    )

    services.add_book_to_shelf(
        shelf,
        user=request.user,
        entry=entry,
    )

    messages.success(
        request,
        f"✅ Книгу додано на полицю «{shelf.name}».",
    )
    return redirect(
        "books:shelf_detail",
        pk=shelf.pk,
    )


@login_required
@require_POST
def shelf_remove_book(
    request: HttpRequest,
    pk: int,
    entry_id: int,
) -> HttpResponse:
    shelf = get_object_or_404(
        Shelf,
        pk=pk,
        user=request.user,
    )
    entry = _get_user_entry_or_404(
        request.user,
        entry_id,
    )

    services.remove_book_from_shelf(
        shelf,
        user=request.user,
        entry=entry,
    )

    messages.warning(
        request,
        f"Книгу прибрано з полиці «{shelf.name}».",
    )
    return redirect(
        "books:shelf_detail",
        pk=shelf.pk,
    )


def public_shelf_list(
    request: HttpRequest,
) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    shelves = selectors.get_public_shelves(
        search=search or None
    )

    return render(
        request,
        "books/public_shelf_list.html",
        {
            "page_obj": _paginate(
                request,
                shelves,
                per_page=12,
            ),
            "search": search,
        },
    )


def public_shelf_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        shelf = selectors.get_public_shelf_detail(pk)
    except Shelf.DoesNotExist as error:
        raise Http404(
            "Публічну полицю не знайдено."
        ) from error

    return render(
        request,
        "books/public_shelf_detail.html",
        {"shelf": shelf},
    )


# =============================================================================
# НОТАТКИ ДО КНИГ
# =============================================================================

@login_required
def note_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    note_type = request.GET.get("type") or None
    pinned = _optional_bool(
        request.GET.get("pinned")
    )
    entry_id = _optional_int(
        request.GET.get("entry")
    )

    notes = selectors.get_user_notes(
        request.user,
        library_entry=entry_id,
        note_type=note_type,
        pinned=pinned,
        search=search or None,
    )

    return render(
        request,
        "books/note_list.html",
        {
            "page_obj": _paginate(
                request,
                notes,
                per_page=15,
            ),
            "search": search,
            "active_type": note_type,
            "active_pinned": pinned,
            "active_entry_id": entry_id,
            "note_types": BookNote.NoteType.choices,
            "library_entries": (
                selectors.get_user_library_choices(
                    request.user
                )
            ),
        },
    )


@login_required
def note_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        note = selectors.get_book_note_detail(
            request.user,
            pk,
        )
    except BookNote.DoesNotExist as error:
        raise Http404("Нотатку не знайдено.") from error

    return render(
        request,
        "books/note_detail.html",
        {"note": note},
    )


@login_required
def note_create(
    request: HttpRequest,
    entry_id: int | None = None,
) -> HttpResponse:
    entry = None

    if entry_id is not None:
        entry = _get_user_entry_or_404(
            request.user,
            entry_id,
        )

    form = BookNoteForm(
        request.POST or None,
        user=request.user,
        library_entry=entry,
    )

    if request.method == "POST" and form.is_valid():
        try:
            note = services.create_book_note(
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Нотатку створено.",
            )
            return redirect(
                "books:note_detail",
                pk=note.pk,
            )

    return render(
        request,
        "books/note_form.html",
        {
            "form": form,
            "entry": entry,
            "title": "Нова нотатка",
        },
    )


@login_required
def note_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    note = get_object_or_404(
        BookNote.objects.select_related(
            "library_entry",
            "library_entry__book",
        ),
        pk=pk,
        library_entry__user=request.user,
    )

    form = BookNoteForm(
        request.POST or None,
        instance=note,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            note = services.update_book_note(
                note,
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Нотатку оновлено.",
            )
            return redirect(
                "books:note_detail",
                pk=note.pk,
            )

    return render(
        request,
        "books/note_form.html",
        {
            "form": form,
            "note": note,
            "title": "Редагувати нотатку",
        },
    )


@login_required
def note_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    note = get_object_or_404(
        BookNote.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )
    entry_id = note.library_entry_id

    if request.method == "POST":
        services.delete_book_note(
            note,
            user=request.user,
        )
        messages.warning(
            request,
            "🗑️ Нотатку видалено.",
        )
        return redirect(
            "books:library_detail",
            pk=entry_id,
        )

    return render(
        request,
        "books/note_confirm_delete.html",
        {"note": note},
    )


@login_required
@require_POST
def note_toggle_pin(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    note = get_object_or_404(
        BookNote.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )
    note = services.toggle_book_note_pin(
        note,
        user=request.user,
    )

    messages.success(
        request,
        (
            "📌 Нотатку закріплено."
            if note.is_pinned
            else "Нотатку відкріплено."
        ),
    )

    return _redirect_to_next(
        request,
        "books:note_detail",
        pk=note.pk,
    )


# =============================================================================
# ЗАКЛАДКИ
# =============================================================================

@login_required
def bookmark_list(
    request: HttpRequest,
) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    entry_id = _optional_int(
        request.GET.get("entry")
    )

    bookmarks = selectors.get_user_bookmarks(
        request.user,
        library_entry=entry_id,
        search=search or None,
    )

    return render(
        request,
        "books/bookmark_list.html",
        {
            "page_obj": _paginate(
                request,
                bookmarks,
                per_page=20,
            ),
            "search": search,
            "active_entry_id": entry_id,
            "library_entries": (
                selectors.get_user_library_choices(
                    request.user
                )
            ),
        },
    )


@login_required
def bookmark_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        bookmark = selectors.get_bookmark_detail(
            request.user,
            pk,
        )
    except Bookmark.DoesNotExist as error:
        raise Http404("Закладку не знайдено.") from error

    return render(
        request,
        "books/bookmark_detail.html",
        {"bookmark": bookmark},
    )


@login_required
def bookmark_create(
    request: HttpRequest,
    entry_id: int | None = None,
) -> HttpResponse:
    entry = None

    if entry_id is not None:
        entry = _get_user_entry_or_404(
            request.user,
            entry_id,
        )

    form = BookmarkForm(
        request.POST or None,
        user=request.user,
        library_entry=entry,
    )

    if request.method == "POST" and form.is_valid():
        try:
            bookmark = services.create_bookmark(
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Закладку створено.",
            )
            return redirect(
                "books:bookmark_detail",
                pk=bookmark.pk,
            )

    return render(
        request,
        "books/bookmark_form.html",
        {
            "form": form,
            "entry": entry,
            "title": "Нова закладка",
        },
    )


@login_required
def bookmark_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    bookmark = get_object_or_404(
        Bookmark.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )

    form = BookmarkForm(
        request.POST or None,
        instance=bookmark,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            bookmark = services.update_bookmark(
                bookmark,
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Закладку оновлено.",
            )
            return redirect(
                "books:bookmark_detail",
                pk=bookmark.pk,
            )

    return render(
        request,
        "books/bookmark_form.html",
        {
            "form": form,
            "bookmark": bookmark,
            "title": "Редагувати закладку",
        },
    )


@login_required
def bookmark_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    bookmark = get_object_or_404(
        Bookmark.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )
    entry_id = bookmark.library_entry_id

    if request.method == "POST":
        services.delete_bookmark(
            bookmark,
            user=request.user,
        )
        messages.warning(
            request,
            "🗑️ Закладку видалено.",
        )
        return redirect(
            "books:library_detail",
            pk=entry_id,
        )

    return render(
        request,
        "books/bookmark_confirm_delete.html",
        {"bookmark": bookmark},
    )


# =============================================================================
# ЦИТАТИ
# =============================================================================

@login_required
def quote_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    favorite = _optional_bool(
        request.GET.get("favorite")
    )
    entry_id = _optional_int(
        request.GET.get("entry")
    )

    quotes = selectors.get_user_quotes(
        request.user,
        library_entry=entry_id,
        favorite=favorite,
        search=search or None,
    )

    return render(
        request,
        "books/quote_list.html",
        {
            "page_obj": _paginate(
                request,
                quotes,
                per_page=15,
            ),
            "search": search,
            "active_favorite": favorite,
            "active_entry_id": entry_id,
            "library_entries": (
                selectors.get_user_library_choices(
                    request.user
                )
            ),
        },
    )


@login_required
def quote_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        quote = selectors.get_quote_detail(
            request.user,
            pk,
        )
    except Quote.DoesNotExist as error:
        raise Http404("Цитату не знайдено.") from error

    return render(
        request,
        "books/quote_detail.html",
        {"quote": quote},
    )


@login_required
def quote_create(
    request: HttpRequest,
    entry_id: int | None = None,
) -> HttpResponse:
    entry = None

    if entry_id is not None:
        entry = _get_user_entry_or_404(
            request.user,
            entry_id,
        )

    form = QuoteForm(
        request.POST or None,
        user=request.user,
        library_entry=entry,
    )

    if request.method == "POST" and form.is_valid():
        try:
            quote = services.create_quote(
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Цитату збережено.",
            )
            return redirect(
                "books:quote_detail",
                pk=quote.pk,
            )

    return render(
        request,
        "books/quote_form.html",
        {
            "form": form,
            "entry": entry,
            "title": "Нова цитата",
        },
    )


@login_required
def quote_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    quote = get_object_or_404(
        Quote.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )

    form = QuoteForm(
        request.POST or None,
        instance=quote,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            quote = services.update_quote(
                quote,
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Цитату оновлено.",
            )
            return redirect(
                "books:quote_detail",
                pk=quote.pk,
            )

    return render(
        request,
        "books/quote_form.html",
        {
            "form": form,
            "quote": quote,
            "title": "Редагувати цитату",
        },
    )


@login_required
def quote_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    quote = get_object_or_404(
        Quote.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )
    entry_id = quote.library_entry_id

    if request.method == "POST":
        services.delete_quote(
            quote,
            user=request.user,
        )
        messages.warning(
            request,
            "🗑️ Цитату видалено.",
        )
        return redirect(
            "books:library_detail",
            pk=entry_id,
        )

    return render(
        request,
        "books/quote_confirm_delete.html",
        {"quote": quote},
    )


@login_required
@require_POST
def quote_toggle_favorite(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    quote = get_object_or_404(
        Quote.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )
    quote = services.toggle_quote_favorite(
        quote,
        user=request.user,
    )

    messages.success(
        request,
        (
            "⭐ Цитату додано до улюблених."
            if quote.is_favorite
            else "Цитату вилучено з улюблених."
        ),
    )

    return _redirect_to_next(
        request,
        "books:quote_detail",
        pk=quote.pk,
    )


# =============================================================================
# РЕЦЕНЗІЇ
# =============================================================================

@login_required
def review_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    published = _optional_bool(
        request.GET.get("published")
    )

    reviews = selectors.get_user_reviews(
        request.user,
        published=published,
        search=search or None,
    )

    return render(
        request,
        "books/review_list.html",
        {
            "page_obj": _paginate(
                request,
                reviews,
                per_page=12,
            ),
            "search": search,
            "active_published": published,
        },
    )


@login_required
def review_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        review = selectors.get_review_detail(
            request.user,
            pk,
        )
    except Review.DoesNotExist as error:
        raise Http404("Рецензію не знайдено.") from error

    return render(
        request,
        "books/review_detail.html",
        {"review": review},
    )


@login_required
def review_create(
    request: HttpRequest,
    entry_id: int | None = None,
) -> HttpResponse:
    entry = None

    if entry_id is not None:
        entry = _get_user_entry_or_404(
            request.user,
            entry_id,
        )

    form = ReviewForm(
        request.POST or None,
        user=request.user,
        library_entry=entry,
    )

    if request.method == "POST" and form.is_valid():
        try:
            review = services.create_review(
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Рецензію створено.",
            )
            return redirect(
                "books:review_detail",
                pk=review.pk,
            )

    return render(
        request,
        "books/review_form.html",
        {
            "form": form,
            "entry": entry,
            "title": "Нова рецензія",
        },
    )


@login_required
def review_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    review = get_object_or_404(
        Review.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )

    form = ReviewForm(
        request.POST or None,
        instance=review,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            review = services.update_review(
                review,
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Рецензію оновлено.",
            )
            return redirect(
                "books:review_detail",
                pk=review.pk,
            )

    return render(
        request,
        "books/review_form.html",
        {
            "form": form,
            "review": review,
            "title": "Редагувати рецензію",
        },
    )


@login_required
def review_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    review = get_object_or_404(
        Review.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )
    entry_id = review.library_entry_id

    if request.method == "POST":
        services.delete_review(
            review,
            user=request.user,
        )
        messages.warning(
            request,
            "🗑️ Рецензію видалено.",
        )
        return redirect(
            "books:library_detail",
            pk=entry_id,
        )

    return render(
        request,
        "books/review_confirm_delete.html",
        {"review": review},
    )


@login_required
@require_POST
def review_toggle_publication(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    review = get_object_or_404(
        Review.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )
    review = services.toggle_review_publication(
        review,
        user=request.user,
    )

    messages.success(
        request,
        (
            "🌐 Рецензію опубліковано."
            if review.is_published
            else "Рецензію знято з публікації."
        ),
    )

    return redirect(
        "books:review_detail",
        pk=review.pk,
    )


def public_review_list(
    request: HttpRequest,
) -> HttpResponse:
    search = request.GET.get("search", "").strip()
    book_id = _optional_int(
        request.GET.get("book")
    )

    reviews = selectors.get_public_reviews(
        book=book_id,
        search=search or None,
    )

    return render(
        request,
        "books/public_review_list.html",
        {
            "page_obj": _paginate(
                request,
                reviews,
                per_page=12,
            ),
            "search": search,
            "active_book_id": book_id,
        },
    )


def public_review_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        review = selectors.get_public_review_detail(pk)
    except Review.DoesNotExist as error:
        raise Http404(
            "Публічну рецензію не знайдено."
        ) from error

    return render(
        request,
        "books/public_review_detail.html",
        {"review": review},
    )


# =============================================================================
# СЕСІЇ ЧИТАННЯ
# =============================================================================

@login_required
def reading_session_list(
    request: HttpRequest,
) -> HttpResponse:
    entry_id = _optional_int(
        request.GET.get("entry")
    )
    date_from = request.GET.get("date_from") or None
    date_to = request.GET.get("date_to") or None

    sessions = selectors.get_reading_sessions(
        request.user,
        library_entry=entry_id,
        date_from=date_from,
        date_to=date_to,
    )

    return render(
        request,
        "books/reading_session_list.html",
        {
            "page_obj": _paginate(
                request,
                sessions,
                per_page=20,
            ),
            "active_entry_id": entry_id,
            "date_from": date_from,
            "date_to": date_to,
            "library_entries": (
                selectors.get_user_library_choices(
                    request.user
                )
            ),
            "stats": selectors.get_reading_session_stats(
                request.user
            ),
        },
    )


@login_required
def reading_session_detail(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    try:
        session = (
            selectors.get_reading_session_detail(
                request.user,
                pk,
            )
        )
    except ReadingSession.DoesNotExist as error:
        raise Http404(
            "Сесію читання не знайдено."
        ) from error

    return render(
        request,
        "books/reading_session_detail.html",
        {"session": session},
    )


@login_required
def reading_session_create(
    request: HttpRequest,
    entry_id: int | None = None,
) -> HttpResponse:
    entry = None

    if entry_id is not None:
        entry = _get_user_entry_or_404(
            request.user,
            entry_id,
        )

    form = ReadingSessionForm(
        request.POST or None,
        user=request.user,
        library_entry=entry,
    )

    if request.method == "POST" and form.is_valid():
        try:
            session = services.create_reading_session(
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Сесію читання збережено.",
            )
            return redirect(
                "books:reading_session_detail",
                pk=session.pk,
            )

    return render(
        request,
        "books/reading_session_form.html",
        {
            "form": form,
            "entry": entry,
            "title": "Нова сесія читання",
        },
    )


@login_required
def reading_session_update(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    session = get_object_or_404(
        ReadingSession.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )

    form = ReadingSessionForm(
        request.POST or None,
        instance=session,
        user=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            session = services.update_reading_session(
                session,
                user=request.user,
                **form.cleaned_data,
            )
        except ValidationError as error:
            _add_service_errors(form, error)
        else:
            messages.success(
                request,
                "✅ Сесію читання оновлено.",
            )
            return redirect(
                "books:reading_session_detail",
                pk=session.pk,
            )

    return render(
        request,
        "books/reading_session_form.html",
        {
            "form": form,
            "session": session,
            "title": "Редагувати сесію",
        },
    )


@login_required
def reading_session_delete(
    request: HttpRequest,
    pk: int,
) -> HttpResponse:
    session = get_object_or_404(
        ReadingSession.objects.select_related(
            "library_entry"
        ),
        pk=pk,
        library_entry__user=request.user,
    )
    entry_id = session.library_entry_id

    if request.method == "POST":
        services.delete_reading_session(
            session,
            user=request.user,
        )
        messages.warning(
            request,
            "🗑️ Сесію читання видалено.",
        )
        return redirect(
            "books:library_detail",
            pk=entry_id,
        )

    return render(
        request,
        "books/reading_session_confirm_delete.html",
        {"session": session},
    )


# =============================================================================
# СУМІСНІСТЬ ЗІ СТАРИМИ НАЗВАМИ VIEW
# =============================================================================

# Ці псевдоніми дозволяють тимчасово не ламати старий urls.py.
# Після оновлення URL їх можна видалити.

book_main_page = book_list
books_list = book_list
books_detail = book_detail
books_create = book_create
books_edit = book_update
books_delete = book_delete
