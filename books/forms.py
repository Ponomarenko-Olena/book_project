"""
forms.py — crispy-форми книжкового застосунку.

Відповідальність цього модуля:
- опис полів і Bootstrap 5 layout;
- обмеження queryset полів поточним користувачем;
- первинна валідація введених даних;
- формування cleaned_data для service layer.

Форми НЕ виконують бізнес-операції та НЕ зберігають пов'язані об'єкти.
Створення, оновлення, видалення, транзакції та M2M-синхронізація
виконуються у services.py.
"""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    Column,
    Div,
    Field,
    Fieldset,
    HTML,
    Layout,
    Row,
    Submit,
)

from . import selectors
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
# БАЗОВІ КЛАСИ ТА ДОПОМІЖНА ВАЛІДАЦІЯ
# =============================================================================

class CrispyModelForm(forms.ModelForm):
    """
    Базова ModelForm із загальним налаштуванням crispy-forms.

    Важливо:
    цей клас не перевизначає save(). Збереження виконує service layer.
    """

    def setup_helper(
        self,
        *layout_fields,
        form_id: str,
        submit_label: str = "Зберегти",
    ) -> None:
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_id = form_id

        self.helper.layout = Layout(
            *layout_fields,
            HTML('<hr class="my-4">'),
            Div(
                Submit(
                    "submit",
                    submit_label,
                    css_class="btn btn-primary",
                ),
                HTML(
                    '<a href="javascript:history.back()" '
                    'class="btn btn-outline-secondary">'
                    "Скасувати"
                    "</a>"
                ),
                css_class="d-flex gap-2",
            ),
        )


class BookChoiceField(forms.ModelChoiceField):
    """Людинозрозумілий підпис книги у select."""

    def label_from_instance(self, book: Book) -> str:
        authors = ", ".join(
            author.name for author in book.authors.all()
        )

        return (
            f"{book.title} — {authors}"
            if authors
            else book.title
        )


class LibraryEntryChoiceField(forms.ModelChoiceField):
    """Підпис запису особистої бібліотеки у select."""

    def label_from_instance(
        self,
        entry: LibraryEntry,
    ) -> str:
        return (
            f"{entry.book.title} — "
            f"{entry.get_status_display()}"
        )


class LibraryEntryMultipleChoiceField(
    forms.ModelMultipleChoiceField
):
    """Підпис кількох записів бібліотеки у multiselect."""

    def label_from_instance(
        self,
        entry: LibraryEntry,
    ) -> str:
        return (
            f"{entry.book.title} — "
            f"{entry.get_status_display()}"
        )


class LibraryEntryScopedFormMixin:
    """
    Обмежує поле library_entry бібліотекою поточного користувача.

    Параметри конструктора:
        user:
            поточний авторизований користувач;

        library_entry:
            конкретний запис бібліотеки. Коли його передано,
            поле фіксується і повертається у cleaned_data.
    """

    def setup_library_entry_field(
        self,
        *,
        user=None,
        library_entry: LibraryEntry | None = None,
    ) -> None:
        if user is not None:
            queryset = selectors.get_user_library_choices(user)
        elif self.instance.pk:
            queryset = (
                LibraryEntry.objects
                .filter(
                    pk=self.instance.library_entry_id
                )
                .select_related("book")
                .prefetch_related("book__authors")
            )
        else:
            queryset = LibraryEntry.objects.none()

        self.fields["library_entry"].queryset = queryset

        if library_entry is None:
            return

        if (
            user is not None
            and library_entry.user_id != user.id
        ):
            raise ValueError(
                "Цей запис бібліотеки належить "
                "іншому користувачу."
            )

        self.fields["library_entry"].queryset = (
            queryset.filter(pk=library_entry.pk)
        )
        self.fields["library_entry"].initial = library_entry
        self.fields["library_entry"].widget = (
            forms.HiddenInput()
        )
        self.fields["library_entry"].disabled = True


def validate_book_page(
    *,
    page: int | None,
    library_entry: LibraryEntry | None,
) -> None:
    """
    Перевіряє номер сторінки відносно обсягу книги.

    Остаточна перевірка також виконується у services.py,
    оскільки service layer не довіряє лише формі.
    """

    if page is None or library_entry is None:
        return

    total_pages = library_entry.book.pages

    if total_pages and page > total_pages:
        raise ValidationError(
            f"У книзі лише {total_pages} сторінок."
        )


# =============================================================================
# ПРОФІЛЬ
# =============================================================================

class UserProfileForm(CrispyModelForm):

    class Meta:
        model = UserProfile
        fields = [
            "display_name",
            "avatar_url",
            "timezone",
            "bio",
        ]
        labels = {
            "display_name": "Ім’я для відображення",
            "avatar_url": "Посилання на аватар",
            "timezone": "Часовий пояс",
            "bio": "Про себе",
        }
        help_texts = {
            "avatar_url": (
                "Повне посилання на зображення профілю."
            ),
            "timezone": (
                "Наприклад: Europe/Kyiv."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setup_helper(
            Fieldset(
                "Профіль користувача",
                Field(
                    "display_name",
                    placeholder=(
                        "Ім’я, яке бачитимуть інші..."
                    ),
                    autofocus=True,
                ),
                Field(
                    "avatar_url",
                    placeholder=(
                        "https://example.com/avatar.jpg"
                    ),
                ),
                Field(
                    "timezone",
                    placeholder="Europe/Kyiv",
                ),
                Field(
                    "bio",
                    rows=4,
                    placeholder=(
                        "Коротко розкажіть про себе..."
                    ),
                ),
            ),
            form_id="user-profile-form",
            submit_label="Зберегти профіль",
        )


# =============================================================================
# АВТОР
# =============================================================================

class AuthorForm(CrispyModelForm):

    class Meta:
        model = Author
        fields = [
            "name",
            "biography",
            "website",
        ]
        labels = {
            "name": "Ім’я автора",
            "biography": "Біографія",
            "website": "Вебсайт",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setup_helper(
            Fieldset(
                "Інформація про автора",
                Field(
                    "name",
                    placeholder=(
                        "Ім’я та прізвище автора..."
                    ),
                    autofocus=True,
                ),
                Field(
                    "biography",
                    rows=5,
                    placeholder=(
                        "Коротка біографія автора..."
                    ),
                ),
                Field(
                    "website",
                    placeholder="https://example.com",
                ),
            ),
            form_id="author-form",
            submit_label="Зберегти автора",
        )

    def clean_name(self) -> str:
        return self.cleaned_data["name"].strip()


# =============================================================================
# КАТЕГОРІЯ
# =============================================================================

class CategoryForm(CrispyModelForm):

    class Meta:
        model = Category
        fields = [
            "name",
            "parent",
            "description",
        ]
        labels = {
            "name": "Назва категорії",
            "parent": "Батьківська категорія",
            "description": "Опис",
        }
        help_texts = {
            "parent": (
                "Залиште порожнім, якщо це "
                "категорія верхнього рівня."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        queryset = selectors.get_category_choices()

        if self.instance.pk:
            queryset = queryset.exclude(
                pk=self.instance.pk
            )

        self.fields["parent"].queryset = queryset
        self.fields["parent"].empty_label = (
            "── Без батьківської категорії ──"
        )
        self.fields["parent"].required = False

        self.setup_helper(
            Fieldset(
                "Категорія книг",
                Field(
                    "name",
                    placeholder=(
                        "Наприклад: Наукова фантастика"
                    ),
                    autofocus=True,
                ),
                Field("parent"),
                Field(
                    "description",
                    rows=4,
                    placeholder="Опис категорії...",
                ),
            ),
            form_id="category-form",
            submit_label="Зберегти категорію",
        )

    def clean_name(self) -> str:
        return self.cleaned_data["name"].strip()

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")

        if parent is None or not self.instance.pk:
            return parent

        current = parent

        while current is not None:
            if current.pk == self.instance.pk:
                raise ValidationError(
                    "Категорія не може бути вкладена "
                    "сама в себе або у власну "
                    "дочірню категорію."
                )

            current = current.parent

        return parent


# =============================================================================
# КНИГА
# =============================================================================

class BookForm(CrispyModelForm):

    class Meta:
        model = Book
        fields = [
            "title",
            "subtitle",
            "authors",
            "categories",
            "isbn13",
            "publisher",
            "published_year",
            "pages",
            "language",
            "description",
            "cover_url",
            "series_name",
            "series_number",
        ]
        labels = {
            "title": "Назва книги",
            "subtitle": "Підзаголовок",
            "authors": "Автори",
            "categories": "Категорії",
            "isbn13": "ISBN-13",
            "publisher": "Видавництво",
            "published_year": "Рік видання",
            "pages": "Кількість сторінок",
            "language": "Мова",
            "description": "Опис книги",
            "cover_url": "Посилання на обкладинку",
            "series_name": "Назва серії",
            "series_number": "Номер книги в серії",
        }
        help_texts = {
            "authors": (
                "Можна вибрати кількох авторів."
            ),
            "categories": (
                "Книга може належати "
                "до кількох категорій."
            ),
            "isbn13": "13 цифр без дефісів.",
            "series_number": (
                "Наприклад: 1, 2 або 2.5."
            ),
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 6}
            ),
            "authors": forms.SelectMultiple(
                attrs={"size": 6}
            ),
            "categories": forms.SelectMultiple(
                attrs={"size": 6}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["authors"].queryset = (
            selectors.get_author_choices()
        )
        self.fields["categories"].queryset = (
            selectors.get_category_choices()
        )

        self.setup_helper(
            Fieldset(
                "Основна інформація",
                Field(
                    "title",
                    placeholder="Назва книги...",
                    autofocus=True,
                ),
                Field(
                    "subtitle",
                    placeholder="Підзаголовок книги...",
                ),
                Row(
                    Column(
                        Field("authors"),
                        css_class="col-md-6",
                    ),
                    Column(
                        Field("categories"),
                        css_class="col-md-6",
                    ),
                ),
            ),
            Fieldset(
                "Видання",
                Row(
                    Column(
                        Field(
                            "publisher",
                            placeholder=(
                                "Назва видавництва..."
                            ),
                        ),
                        css_class="col-md-6",
                    ),
                    Column(
                        Field(
                            "published_year",
                            placeholder="2026",
                            min=1,
                        ),
                        css_class="col-md-3",
                    ),
                    Column(
                        Field(
                            "pages",
                            placeholder="350",
                            min=1,
                        ),
                        css_class="col-md-3",
                    ),
                ),
                Row(
                    Column(
                        Field(
                            "isbn13",
                            placeholder="9781234567890",
                        ),
                        css_class="col-md-6",
                    ),
                    Column(
                        Field(
                            "language",
                            placeholder="Українська",
                        ),
                        css_class="col-md-6",
                    ),
                ),
            ),
            Fieldset(
                "Серія книг",
                Row(
                    Column(
                        Field(
                            "series_name",
                            placeholder="Назва серії...",
                        ),
                        css_class="col-md-8",
                    ),
                    Column(
                        Field(
                            "series_number",
                            placeholder="1",
                            min=0,
                        ),
                        css_class="col-md-4",
                    ),
                ),
            ),
            Fieldset(
                "Опис та обкладинка",
                Field(
                    "description",
                    rows=6,
                    placeholder="Опис книги...",
                ),
                Field(
                    "cover_url",
                    placeholder=(
                        "https://example.com/cover.jpg"
                    ),
                ),
            ),
            form_id="book-form",
            submit_label="Зберегти книгу",
        )

    def clean_title(self) -> str:
        return self.cleaned_data["title"].strip()

    def clean_isbn13(self) -> str | None:
        isbn = self.cleaned_data.get("isbn13")

        if not isbn:
            return None

        normalized_isbn = (
            isbn.replace("-", "")
            .replace(" ", "")
            .strip()
        )

        if (
            not normalized_isbn.isdigit()
            or len(normalized_isbn) != 13
        ):
            raise ValidationError(
                "ISBN-13 повинен містити "
                "рівно 13 цифр."
            )

        queryset = Book.objects.filter(
            isbn13=normalized_isbn
        )

        if self.instance.pk:
            queryset = queryset.exclude(
                pk=self.instance.pk
            )

        if queryset.exists():
            raise ValidationError(
                "Книга з таким ISBN уже існує."
            )

        return normalized_isbn


# =============================================================================
# ОСОБИСТИЙ ТЕГ
# =============================================================================

class PersonalTagForm(CrispyModelForm):
    """
    Форма не встановлює user і не викликає save().

    Використання:
        services.create_personal_tag(
            user=request.user,
            **form.cleaned_data,
        )
    """

    class Meta:
        model = PersonalTag
        fields = [
            "name",
            "color",
        ]
        labels = {
            "name": "Назва тегу",
            "color": "Колір",
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        self.fields["color"].widget = forms.TextInput(
            attrs={
                "type": "color",
                "class": (
                    "form-control "
                    "form-control-color"
                ),
            }
        )

        if not self.initial.get("color"):
            self.initial["color"] = "#3498db"

        self.setup_helper(
            Fieldset(
                "Особистий тег",
                Row(
                    Column(
                        Field(
                            "name",
                            placeholder=(
                                "Наприклад: Для роботи"
                            ),
                            autofocus=True,
                        ),
                        css_class="col-md-9",
                    ),
                    Column(
                        Field("color"),
                        css_class="col-md-3",
                    ),
                ),
            ),
            form_id="personal-tag-form",
            submit_label="Зберегти тег",
        )

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()

        if self.user is None:
            return name

        duplicate_exists = (
            PersonalTag.objects
            .filter(
                user=self.user,
                name__iexact=name,
            )
            .exclude(
                pk=self.instance.pk
                if self.instance.pk
                else None
            )
            .exists()
        )

        if duplicate_exists:
            raise ValidationError(
                "У вас уже існує тег "
                "із такою назвою."
            )

        return name


# =============================================================================
# ЗАПИС ОСОБИСТОЇ БІБЛІОТЕКИ
# =============================================================================

class LibraryEntryForm(CrispyModelForm):
    """
    Повертає cleaned_data, сумісний із:
        services.create_library_entry(...)
        services.update_library_entry(...)

    user і M2M-теги зберігає service layer.
    """

    book = BookChoiceField(
        queryset=Book.objects.none(),
        label="Книга",
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=PersonalTag.objects.none(),
        required=False,
        label="Особисті теги",
        help_text=(
            "Можна вибрати кілька власних тегів."
        ),
    )

    class Meta:
        model = LibraryEntry
        fields = [
            "book",
            "status",
            "book_format",
            "visibility",
            "current_page",
            "rating",
            "is_favorite",
            "is_owned",
            "started_at",
            "finished_at",
            "tags",
        ]
        labels = {
            "book": "Книга",
            "status": "Статус читання",
            "book_format": "Формат",
            "visibility": "Видимість",
            "current_page": "Поточна сторінка",
            "rating": "Оцінка",
            "is_favorite": (
                "Додати до улюблених"
            ),
            "is_owned": (
                "Книга є у власності"
            ),
            "started_at": "Початок читання",
            "finished_at": "Завершення читання",
            "tags": "Особисті теги",
        }
        help_texts = {
            "rating": "Оцінка від 1 до 5.",
            "current_page": (
                "Відсоток прогресу "
                "розрахує service layer."
            ),
        }
        widgets = {
            "started_at": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "finished_at": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "tags": forms.SelectMultiple(
                attrs={"size": 5}
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        book: Book | None = None,
        **kwargs,
    ):
        self.user = user
        super().__init__(*args, **kwargs)

        self.fields["book"].queryset = (
            selectors.get_book_choices()
        )
        self.fields["tags"].queryset = (
            selectors.get_user_tag_choices(user)
            if user is not None
            else PersonalTag.objects.none()
        )

        self.fields["started_at"].input_formats = [
            "%Y-%m-%d"
        ]
        self.fields["finished_at"].input_formats = [
            "%Y-%m-%d"
        ]

        if self.instance.pk:
            self.initial["tags"] = (
                self.instance.tags.all()
            )

        if book is not None:
            self.fields["book"].queryset = (
                selectors.get_book_choices()
                .filter(pk=book.pk)
            )
            self.fields["book"].initial = book
            self.fields["book"].widget = (
                forms.HiddenInput()
            )
            self.fields["book"].disabled = True

        self.setup_helper(
            Fieldset(
                "Книга",
                Field("book"),
            ),
            Fieldset(
                "Стан читання",
                Row(
                    Column(
                        Field("status"),
                        css_class="col-md-4",
                    ),
                    Column(
                        Field("book_format"),
                        css_class="col-md-4",
                    ),
                    Column(
                        Field("visibility"),
                        css_class="col-md-4",
                    ),
                ),
                Row(
                    Column(
                        Field(
                            "current_page",
                            min=0,
                            placeholder="0",
                        ),
                        css_class="col-md-6",
                    ),
                    Column(
                        Field(
                            "rating",
                            min=1,
                            max=5,
                            placeholder="1–5",
                        ),
                        css_class="col-md-6",
                    ),
                ),
                Row(
                    Column(
                        Field("started_at"),
                        css_class="col-md-6",
                    ),
                    Column(
                        Field("finished_at"),
                        css_class="col-md-6",
                    ),
                ),
            ),
            Fieldset(
                "Організація бібліотеки",
                Field("tags", size=5),
                Row(
                    Column(
                        Div(
                            Field("is_favorite"),
                            css_class="form-check",
                        ),
                        css_class="col-md-6",
                    ),
                    Column(
                        Div(
                            Field("is_owned"),
                            css_class="form-check",
                        ),
                        css_class="col-md-6",
                    ),
                ),
            ),
            form_id="library-entry-form",
            submit_label="Зберегти в бібліотеці",
        )

    def clean(self):
        cleaned_data = super().clean()

        book = cleaned_data.get("book")
        current_page = cleaned_data.get(
            "current_page"
        )
        started_at = cleaned_data.get(
            "started_at"
        )
        finished_at = cleaned_data.get(
            "finished_at"
        )

        if (
            book is not None
            and current_page is not None
            and book.pages
            and current_page > book.pages
        ):
            self.add_error(
                "current_page",
                f"У книзі лише {book.pages} сторінок.",
            )

        if (
            started_at is not None
            and finished_at is not None
            and finished_at < started_at
        ):
            self.add_error(
                "finished_at",
                "Дата завершення не може бути "
                "раніше дати початку.",
            )

        if self.user is not None and book is not None:
            duplicate_query = (
                LibraryEntry.objects
                .filter(
                    user=self.user,
                    book=book,
                )
            )

            if self.instance.pk:
                duplicate_query = (
                    duplicate_query.exclude(
                        pk=self.instance.pk
                    )
                )

            if duplicate_query.exists():
                self.add_error(
                    "book",
                    "Ця книга вже є "
                    "у вашій бібліотеці.",
                )

        return cleaned_data


# =============================================================================
# ПОЛИЦЯ
# =============================================================================

class ShelfForm(CrispyModelForm):
    """
    Повертає cleaned_data, сумісний із:
        services.create_shelf(...)
        services.update_shelf(...)

    Синхронізацію ShelfItem виконує service layer.
    """

    books = LibraryEntryMultipleChoiceField(
        queryset=LibraryEntry.objects.none(),
        required=False,
        label="Книги на полиці",
    )

    class Meta:
        model = Shelf
        fields = [
            "name",
            "description",
            "is_public",
            "books",
        ]
        labels = {
            "name": "Назва полиці",
            "description": "Опис",
            "is_public": "Публічна полиця",
            "books": "Книги",
        }
        help_texts = {
            "is_public": (
                "Публічну полицю зможуть "
                "переглядати інші користувачі."
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        self.fields["books"].queryset = (
            selectors.get_user_library_choices(user)
            if user is not None
            else LibraryEntry.objects.none()
        )

        if self.instance.pk:
            self.initial["books"] = (
                self.instance.books.all()
            )

        self.setup_helper(
            Fieldset(
                "Книжкова полиця",
                Field(
                    "name",
                    placeholder=(
                        "Наприклад: Книги для роботи"
                    ),
                    autofocus=True,
                ),
                Field(
                    "description",
                    rows=4,
                    placeholder="Опис полиці...",
                ),
                Field("books", size=8),
                Div(
                    Field("is_public"),
                    css_class="form-check",
                ),
            ),
            form_id="shelf-form",
            submit_label="Зберегти полицю",
        )

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()

        if self.user is None:
            return name

        duplicate_query = Shelf.objects.filter(
            user=self.user,
            name__iexact=name,
        )

        if self.instance.pk:
            duplicate_query = (
                duplicate_query.exclude(
                    pk=self.instance.pk
                )
            )

        if duplicate_query.exists():
            raise ValidationError(
                "У вас уже є полиця "
                "з такою назвою."
            )

        return name


# =============================================================================
# НОТАТКА
# =============================================================================

class BookNoteForm(
    LibraryEntryScopedFormMixin,
    CrispyModelForm,
):
    library_entry = LibraryEntryChoiceField(
        queryset=LibraryEntry.objects.none(),
        label="Книга",
    )

    class Meta:
        model = BookNote
        fields = [
            "library_entry",
            "note_type",
            "title",
            "body",
            "page",
            "is_pinned",
        ]
        labels = {
            "library_entry": "Книга",
            "note_type": "Тип нотатки",
            "title": "Заголовок",
            "body": "Текст нотатки",
            "page": "Сторінка",
            "is_pinned": "Закріпити нотатку",
        }

    def __init__(
        self,
        *args,
        user=None,
        library_entry=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.setup_library_entry_field(
            user=user,
            library_entry=library_entry,
        )

        self.setup_helper(
            Fieldset(
                "Книга",
                Field("library_entry"),
            ),
            Fieldset(
                "Нотатка",
                Row(
                    Column(
                        Field("note_type"),
                        css_class="col-md-8",
                    ),
                    Column(
                        Field(
                            "page",
                            min=1,
                            placeholder="Сторінка",
                        ),
                        css_class="col-md-4",
                    ),
                ),
                Field(
                    "title",
                    placeholder=(
                        "Заголовок нотатки..."
                    ),
                    autofocus=True,
                ),
                Field(
                    "body",
                    rows=7,
                    placeholder="Текст нотатки...",
                ),
                Div(
                    Field("is_pinned"),
                    css_class="form-check",
                ),
            ),
            form_id="book-note-form",
            submit_label="Зберегти нотатку",
        )

    def clean_page(self):
        page = self.cleaned_data.get("page")
        entry = self.cleaned_data.get(
            "library_entry"
        )

        validate_book_page(
            page=page,
            library_entry=entry,
        )
        return page


# =============================================================================
# ЗАКЛАДКА
# =============================================================================

class BookmarkForm(
    LibraryEntryScopedFormMixin,
    CrispyModelForm,
):
    library_entry = LibraryEntryChoiceField(
        queryset=LibraryEntry.objects.none(),
        label="Книга",
    )

    class Meta:
        model = Bookmark
        fields = [
            "library_entry",
            "page",
            "position",
            "label",
            "comment",
        ]
        labels = {
            "library_entry": "Книга",
            "page": "Сторінка",
            "position": "Позиція",
            "label": "Назва закладки",
            "comment": "Коментар",
        }
        help_texts = {
            "position": (
                "Для електронної чи аудіокниги: "
                "35%, розділ 4 або 01:24:30."
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        library_entry=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.setup_library_entry_field(
            user=user,
            library_entry=library_entry,
        )

        self.setup_helper(
            Fieldset(
                "Книга",
                Field("library_entry"),
            ),
            Fieldset(
                "Закладка",
                Field(
                    "label",
                    placeholder=(
                        "Наприклад: Продовжити читання"
                    ),
                    autofocus=True,
                ),
                Row(
                    Column(
                        Field(
                            "page",
                            min=1,
                            placeholder="135",
                        ),
                        css_class="col-md-4",
                    ),
                    Column(
                        Field(
                            "position",
                            placeholder=(
                                "35%, глава 4 "
                                "або 01:24:30"
                            ),
                        ),
                        css_class="col-md-8",
                    ),
                ),
                Field(
                    "comment",
                    rows=4,
                    placeholder=(
                        "Коментар до закладки..."
                    ),
                ),
            ),
            form_id="bookmark-form",
            submit_label="Зберегти закладку",
        )

    def clean(self):
        cleaned_data = super().clean()

        page = cleaned_data.get("page")
        position = (
            cleaned_data.get("position") or ""
        ).strip()
        entry = cleaned_data.get(
            "library_entry"
        )

        if page is None and not position:
            raise ValidationError(
                "Вкажіть сторінку або позицію "
                "в електронній чи аудіокнизі."
            )

        validate_book_page(
            page=page,
            library_entry=entry,
        )

        cleaned_data["position"] = position
        return cleaned_data


# =============================================================================
# ЦИТАТА
# =============================================================================

class QuoteForm(
    LibraryEntryScopedFormMixin,
    CrispyModelForm,
):
    library_entry = LibraryEntryChoiceField(
        queryset=LibraryEntry.objects.none(),
        label="Книга",
    )

    class Meta:
        model = Quote
        fields = [
            "library_entry",
            "text",
            "page",
            "comment",
            "is_favorite",
        ]
        labels = {
            "library_entry": "Книга",
            "text": "Текст цитати",
            "page": "Сторінка",
            "comment": "Мій коментар",
            "is_favorite": "Улюблена цитата",
        }

    def __init__(
        self,
        *args,
        user=None,
        library_entry=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.setup_library_entry_field(
            user=user,
            library_entry=library_entry,
        )

        self.setup_helper(
            Fieldset(
                "Книга",
                Field("library_entry"),
            ),
            Fieldset(
                "Цитата",
                Field(
                    "text",
                    rows=5,
                    placeholder=(
                        "Введіть текст цитати..."
                    ),
                    autofocus=True,
                ),
                Field(
                    "page",
                    min=1,
                    placeholder="Сторінка...",
                ),
                Field(
                    "comment",
                    rows=4,
                    placeholder=(
                        "Ваш коментар до цитати..."
                    ),
                ),
                Div(
                    Field("is_favorite"),
                    css_class="form-check",
                ),
            ),
            form_id="quote-form",
            submit_label="Зберегти цитату",
        )

    def clean_page(self):
        page = self.cleaned_data.get("page")
        entry = self.cleaned_data.get(
            "library_entry"
        )

        validate_book_page(
            page=page,
            library_entry=entry,
        )
        return page


# =============================================================================
# РЕЦЕНЗІЯ
# =============================================================================

class ReviewForm(
    LibraryEntryScopedFormMixin,
    CrispyModelForm,
):
    library_entry = LibraryEntryChoiceField(
        queryset=LibraryEntry.objects.none(),
        label="Книга",
    )

    class Meta:
        model = Review
        fields = [
            "library_entry",
            "title",
            "text",
            "contains_spoilers",
            "is_published",
        ]
        labels = {
            "library_entry": "Книга",
            "title": "Заголовок рецензії",
            "text": "Текст рецензії",
            "contains_spoilers": (
                "Рецензія містить спойлери"
            ),
            "is_published": (
                "Опублікувати рецензію"
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        library_entry=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.setup_library_entry_field(
            user=user,
            library_entry=library_entry,
        )

        queryset = self.fields[
            "library_entry"
        ].queryset

        if self.instance.pk:
            queryset = queryset.filter(
                Q(review__isnull=True)
                | Q(
                    pk=(
                        self.instance
                        .library_entry_id
                    )
                )
            )
        else:
            queryset = queryset.filter(
                review__isnull=True
            )

        self.fields[
            "library_entry"
        ].queryset = queryset

        self.setup_helper(
            Fieldset(
                "Книга",
                Field("library_entry"),
            ),
            Fieldset(
                "Рецензія",
                Field(
                    "title",
                    placeholder=(
                        "Заголовок рецензії..."
                    ),
                    autofocus=True,
                ),
                Field(
                    "text",
                    rows=10,
                    placeholder=(
                        "Ваші враження від книги..."
                    ),
                ),
                Row(
                    Column(
                        Div(
                            Field(
                                "contains_spoilers"
                            ),
                            css_class="form-check",
                        ),
                        css_class="col-md-6",
                    ),
                    Column(
                        Div(
                            Field("is_published"),
                            css_class="form-check",
                        ),
                        css_class="col-md-6",
                    ),
                ),
            ),
            form_id="review-form",
            submit_label="Зберегти рецензію",
        )


# =============================================================================
# СЕСІЯ ЧИТАННЯ
# =============================================================================

class ReadingSessionForm(
    LibraryEntryScopedFormMixin,
    CrispyModelForm,
):
    library_entry = LibraryEntryChoiceField(
        queryset=LibraryEntry.objects.none(),
        label="Книга",
    )

    class Meta:
        model = ReadingSession
        fields = [
            "library_entry",
            "started_at",
            "finished_at",
            "start_page",
            "end_page",
            "note",
        ]
        labels = {
            "library_entry": "Книга",
            "started_at": "Початок читання",
            "finished_at": "Завершення читання",
            "start_page": "Початкова сторінка",
            "end_page": "Кінцева сторінка",
            "note": "Коментар",
        }
        widgets = {
            "started_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "type": "datetime-local"
                },
            ),
            "finished_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "type": "datetime-local"
                },
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        library_entry=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.fields["started_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]
        self.fields["finished_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]

        self.setup_library_entry_field(
            user=user,
            library_entry=library_entry,
        )

        self.setup_helper(
            Fieldset(
                "Книга",
                Field("library_entry"),
            ),
            Fieldset(
                "Час читання",
                Row(
                    Column(
                        Field("started_at"),
                        css_class="col-md-6",
                    ),
                    Column(
                        Field("finished_at"),
                        css_class="col-md-6",
                    ),
                ),
            ),
            Fieldset(
                "Прогрес",
                Row(
                    Column(
                        Field(
                            "start_page",
                            min=0,
                            placeholder="0",
                        ),
                        css_class="col-md-6",
                    ),
                    Column(
                        Field(
                            "end_page",
                            min=0,
                            placeholder="25",
                        ),
                        css_class="col-md-6",
                    ),
                ),
                Field(
                    "note",
                    rows=4,
                    placeholder=(
                        "Що читали та які "
                        "були враження..."
                    ),
                ),
            ),
            form_id="reading-session-form",
            submit_label="Зберегти сесію",
        )

    def clean(self):
        cleaned_data = super().clean()

        entry = cleaned_data.get(
            "library_entry"
        )
        started_at = cleaned_data.get(
            "started_at"
        )
        finished_at = cleaned_data.get(
            "finished_at"
        )
        start_page = cleaned_data.get(
            "start_page"
        )
        end_page = cleaned_data.get(
            "end_page"
        )

        if (
            started_at is not None
            and finished_at is not None
            and finished_at < started_at
        ):
            self.add_error(
                "finished_at",
                "Завершення не може бути "
                "раніше початку.",
            )

        if (
            start_page is not None
            and end_page is not None
            and end_page < start_page
        ):
            self.add_error(
                "end_page",
                "Кінцева сторінка не може "
                "бути меншою за початкову.",
            )

        try:
            validate_book_page(
                page=start_page,
                library_entry=entry,
            )
        except ValidationError as error:
            self.add_error(
                "start_page",
                error,
            )

        try:
            validate_book_page(
                page=end_page,
                library_entry=entry,
            )
        except ValidationError as error:
            self.add_error(
                "end_page",
                error,
            )

        return cleaned_data
