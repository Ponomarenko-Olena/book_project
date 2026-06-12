from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models import Q
from django.utils.text import slugify


def validate_cover_file_size(image):
    """Обмежує розмір завантаженої обкладинки до 5 МБ."""

    max_size = 5 * 1024 * 1024

    if image.size > max_size:
        raise ValidationError(
            "Розмір обкладинки не повинен перевищувати 5 МБ."
        )


# ============================================================================
# БАЗОВА МОДЕЛЬ
# ============================================================================

class TimeStampedModel(models.Model):
    """
    Абстрактна модель, яка додає час створення та оновлення.
    Таблиця для неї в базі даних не створюється.
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Створено",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Оновлено",
    )

    class Meta:
        abstract = True


# ============================================================================
# ПРОФІЛЬ КОРИСТУВАЧА
# ============================================================================

class UserProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Користувач",
    )
    display_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Ім’я для відображення",
    )
    avatar_url = models.URLField(
        blank=True,
        verbose_name="Посилання на аватар",
    )
    timezone = models.CharField(
        max_length=50,
        default="UTC",
        verbose_name="Часовий пояс",
    )
    bio = models.TextField(
        blank=True,
        verbose_name="Про користувача",
    )

    def __str__(self):
        return self.display_name or self.user.get_username()

    class Meta:
        verbose_name = "Профіль користувача"
        verbose_name_plural = "Профілі користувачів"


# ============================================================================
# АВТОРИ
# ============================================================================

class Author(TimeStampedModel):
    name = models.CharField(
        max_length=255,
        verbose_name="Ім’я автора",
    )
    biography = models.TextField(
        blank=True,
        verbose_name="Біографія",
    )
    website = models.URLField(
        blank=True,
        verbose_name="Вебсайт",
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name = "Автор"
        verbose_name_plural = "Автори"
        indexes = [
            models.Index(fields=["name"]),
        ]


# ============================================================================
# КАТЕГОРІЇ
# ============================================================================

class Category(TimeStampedModel):
    """
    Глобальна категорія книги.

    Наприклад:
    - Художня література
        - Фантастика
        - Детективи
    - Наукова література
        - Психологія
        - Програмування
    """

    name = models.CharField(
        max_length=100,
        verbose_name="Назва категорії",
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        blank=True,
        verbose_name="Slug",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Опис",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Батьківська категорія",
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name, allow_unicode=True)
            slug = base_slug
            counter = 2

            while Category.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name = "Категорія"
        verbose_name_plural = "Категорії"


# ============================================================================
# КНИГИ
# ============================================================================

class Book(TimeStampedModel):
    title = models.CharField(
        max_length=255,
        verbose_name="Назва книги",
    )
    subtitle = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Підзаголовок",
    )
    authors = models.ManyToManyField(
        Author,
        related_name="books",
        verbose_name="Автори",
    )
    categories = models.ManyToManyField(
        Category,
        related_name="books",
        blank=True,
        verbose_name="Категорії",
    )

    isbn13 = models.CharField(
        max_length=13,
        unique=True,
        null=True,
        blank=True,
        verbose_name="ISBN-13",
    )
    publisher = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Видавництво",
    )
    published_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Рік видання",
    )
    pages = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Кількість сторінок",
    )
    language = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Мова",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Опис книги",
    )
    cover_image = models.ImageField(
        upload_to="book_covers/%Y/%m/",
        max_length=255,
        blank=True,
        default="",
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "jpg",
                    "jpeg",
                    "png",
                    "webp",
                ]
            ),
            validate_cover_file_size,
        ],
        verbose_name="Файл обкладинки",
        help_text=(
            "JPG, JPEG, PNG або WEBP. "
            "Максимальний розмір — 5 МБ."
        ),
    )
    cover_url = models.URLField(
        blank=True,
        verbose_name="Зовнішнє посилання на обкладинку",
        help_text=(
            "Використовується, якщо файл обкладинки "
            "не завантажено."
        ),
    )

    series_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Серія книг",
    )
    series_number = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Номер у серії",
    )

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_books",
        verbose_name="Хто додав книгу",
    )

    @property
    def cover_source(self):
        """
        Повертає локально завантажену обкладинку,
        а за її відсутності — зовнішнє посилання.
        """

        if self.cover_image:
            try:
                return self.cover_image.url
            except ValueError:
                pass

        return self.cover_url or ""

    @property
    def authors_display(self):
        if not self.pk:
            return ""

        return ", ".join(
            self.authors.values_list("name", flat=True)
        )

    def __str__(self):
        if not self.pk:
            return self.title

        authors = self.authors_display

        if authors:
            return f"{self.title} — {authors}"

        return self.title

    class Meta:
        ordering = ["title"]
        verbose_name = "Книга"
        verbose_name_plural = "Книги"
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["published_year"]),
            models.Index(fields=["isbn13"]),
        ]


# ============================================================================
# ОСОБИСТІ ТЕГИ
# ============================================================================

class PersonalTag(TimeStampedModel):
    """
    Особисті мітки користувача.

    Наприклад:
    - для роботи;
    - для дисертації;
    - прочитати влітку;
    - важливе.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="book_tags",
        verbose_name="Користувач",
    )
    name = models.CharField(
        max_length=50,
        verbose_name="Назва тегу",
    )
    color = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Колір",
        help_text="Наприклад: #3498db",
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name = "Особистий тег"
        verbose_name_plural = "Особисті теги"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_personal_tag_per_user",
            ),
        ]


# ============================================================================
# КНИГА В БІБЛІОТЕЦІ КОРИСТУВАЧА
# ============================================================================

class LibraryEntry(TimeStampedModel):

    class ReadingStatus(models.TextChoices):
        WANT_TO_READ = "want_to_read", "Хочу прочитати"
        READING = "reading", "Читаю"
        PAUSED = "paused", "Відкладено"
        COMPLETED = "completed", "Прочитано"
        DROPPED = "dropped", "Не дочитано"

    class BookFormat(models.TextChoices):
        PAPER = "paper", "Паперова книга"
        EBOOK = "ebook", "Електронна книга"
        AUDIOBOOK = "audiobook", "Аудіокнига"
        OTHER = "other", "Інший формат"

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Приватна"
        FRIENDS = "friends", "Для друзів"
        PUBLIC = "public", "Публічна"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="library_entries",
        verbose_name="Користувач",
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="library_entries",
        verbose_name="Книга",
    )

    status = models.CharField(
        max_length=20,
        choices=ReadingStatus.choices,
        default=ReadingStatus.WANT_TO_READ,
        verbose_name="Статус читання",
    )
    book_format = models.CharField(
        max_length=20,
        choices=BookFormat.choices,
        default=BookFormat.PAPER,
        verbose_name="Формат книги",
    )
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
        verbose_name="Видимість",
    )

    current_page = models.PositiveIntegerField(
        default=0,
        verbose_name="Поточна сторінка",
    )
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(100),
        ],
        verbose_name="Прогрес читання",
    )

    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ],
        verbose_name="Особиста оцінка",
    )

    is_favorite = models.BooleanField(
        default=False,
        verbose_name="Улюблена книга",
    )
    is_owned = models.BooleanField(
        default=True,
        verbose_name="Є у власності",
    )

    started_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата початку читання",
    )
    finished_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата завершення читання",
    )

    tags = models.ManyToManyField(
        PersonalTag,
        through="LibraryEntryTag",
        related_name="library_entries",
        blank=True,
        verbose_name="Особисті теги",
    )

    def clean(self):
        errors = {}

        if (
            self.current_page
            and self.book_id
            and self.book.pages
            and self.current_page > self.book.pages
        ):
            errors["current_page"] = (
                "Поточна сторінка не може перевищувати "
                "загальну кількість сторінок книги."
            )

        if (
            self.started_at
            and self.finished_at
            and self.finished_at < self.started_at
        ):
            errors["finished_at"] = (
                "Дата завершення не може бути раніше дати початку."
            )

        if errors:
            raise ValidationError(errors)

    def update_progress_from_page(self):
        """
        Перераховує відсоток прогресу на основі поточної сторінки.
        """

        if not self.book.pages:
            return

        progress = round(
            self.current_page / self.book.pages * 100
        )

        self.progress_percent = min(progress, 100)

    def __str__(self):
        return f"{self.user} — {self.book}"

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Книга в бібліотеці"
        verbose_name_plural = "Книги в бібліотеці"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "book"],
                name="unique_book_in_user_library",
            ),
            models.CheckConstraint(
                condition=Q(progress_percent__gte=0)
                & Q(progress_percent__lte=100),
                name="library_progress_between_0_and_100",
            ),
            models.CheckConstraint(
                condition=Q(rating__isnull=True)
                | Q(rating__gte=1, rating__lte=5),
                name="library_rating_between_1_and_5",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "is_favorite"]),
            models.Index(fields=["user", "-updated_at"]),
        ]


class LibraryEntryTag(models.Model):
    """
    Проміжна таблиця між книгою в бібліотеці та особистим тегом.
    """

    library_entry = models.ForeignKey(
        LibraryEntry,
        on_delete=models.CASCADE,
        related_name="tag_links",
        verbose_name="Запис бібліотеки",
    )
    tag = models.ForeignKey(
        PersonalTag,
        on_delete=models.CASCADE,
        related_name="entry_links",
        verbose_name="Тег",
    )

    def clean(self):
        if (
            self.library_entry_id
            and self.tag_id
            and self.library_entry.user_id != self.tag.user_id
        ):
            raise ValidationError(
                "Не можна додати тег іншого користувача."
            )

    def __str__(self):
        return f"{self.library_entry} — {self.tag}"

    class Meta:
        verbose_name = "Тег книги"
        verbose_name_plural = "Теги книг"
        constraints = [
            models.UniqueConstraint(
                fields=["library_entry", "tag"],
                name="unique_tag_for_library_entry",
            ),
        ]


# ============================================================================
# ВЛАСНІ ПОЛИЦІ
# ============================================================================

class Shelf(TimeStampedModel):
    """
    Власна добірка користувача.

    Наприклад:
    - Для роботи;
    - Найкраща фантастика;
    - Книги на 2026 рік;
    - Література для курсу Python.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="book_shelves",
        verbose_name="Користувач",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Назва полиці",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Опис",
    )
    is_public = models.BooleanField(
        default=False,
        verbose_name="Публічна полиця",
    )

    books = models.ManyToManyField(
        LibraryEntry,
        through="ShelfItem",
        related_name="shelves",
        blank=True,
        verbose_name="Книги",
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name = "Книжкова полиця"
        verbose_name_plural = "Книжкові полиці"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_shelf_name_per_user",
            ),
        ]


class ShelfItem(models.Model):
    shelf = models.ForeignKey(
        Shelf,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Полиця",
    )
    library_entry = models.ForeignKey(
        LibraryEntry,
        on_delete=models.CASCADE,
        related_name="shelf_items",
        verbose_name="Книга",
    )
    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Додано",
    )

    def clean(self):
        if (
            self.shelf_id
            and self.library_entry_id
            and self.shelf.user_id != self.library_entry.user_id
        ):
            raise ValidationError(
                "Не можна додати до полиці книгу іншого користувача."
            )

    def __str__(self):
        return f"{self.shelf}: {self.library_entry.book}"

    class Meta:
        verbose_name = "Книга на полиці"
        verbose_name_plural = "Книги на полицях"
        constraints = [
            models.UniqueConstraint(
                fields=["shelf", "library_entry"],
                name="unique_book_on_shelf",
            ),
        ]


# ============================================================================
# НОТАТКИ
# ============================================================================

class BookNote(TimeStampedModel):

    class NoteType(models.TextChoices):
        NOTE = "note", "Звичайна нотатка"
        SUMMARY = "summary", "Конспект"
        IDEA = "idea", "Власна думка"
        QUESTION = "question", "Питання"
        TODO = "todo", "Потрібно опрацювати"

    library_entry = models.ForeignKey(
        LibraryEntry,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name="Книга",
    )
    note_type = models.CharField(
        max_length=20,
        choices=NoteType.choices,
        default=NoteType.NOTE,
        verbose_name="Тип нотатки",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Заголовок",
    )
    body = models.TextField(
        verbose_name="Текст нотатки",
    )
    page = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Сторінка",
    )
    is_pinned = models.BooleanField(
        default=False,
        verbose_name="Закріплена",
    )

    def __str__(self):
        return self.title or f"Нотатка до {self.library_entry.book.title}"

    class Meta:
        ordering = ["-is_pinned", "-updated_at"]
        verbose_name = "Нотатка"
        verbose_name_plural = "Нотатки"
        indexes = [
            models.Index(fields=["library_entry", "-updated_at"]),
        ]


# ============================================================================
# ЗАКЛАДКИ
# ============================================================================

class Bookmark(TimeStampedModel):
    library_entry = models.ForeignKey(
        LibraryEntry,
        on_delete=models.CASCADE,
        related_name="bookmarks",
        verbose_name="Книга",
    )
    page = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Сторінка",
    )
    position = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Позиція в електронній або аудіокнизі",
        help_text="Наприклад: 35%, глава 4 або 01:24:30",
    )
    label = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Назва закладки",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Коментар",
    )

    def __str__(self):
        location = self.page or self.position or "без позиції"
        return f"{self.library_entry.book.title}: {location}"

    class Meta:
        ordering = ["page", "created_at"]
        verbose_name = "Закладка"
        verbose_name_plural = "Закладки"


# ============================================================================
# ЦИТАТИ
# ============================================================================

class Quote(TimeStampedModel):
    library_entry = models.ForeignKey(
        LibraryEntry,
        on_delete=models.CASCADE,
        related_name="quotes",
        verbose_name="Книга",
    )
    text = models.TextField(
        verbose_name="Текст цитати",
    )
    page = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Сторінка",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Коментар",
    )
    is_favorite = models.BooleanField(
        default=False,
        verbose_name="Улюблена цитата",
    )

    def __str__(self):
        shortened_text = self.text[:60]
        return f"{self.library_entry.book.title}: {shortened_text}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Цитата"
        verbose_name_plural = "Цитати"


# ============================================================================
# РЕЦЕНЗІЯ
# ============================================================================

class Review(TimeStampedModel):
    library_entry = models.OneToOneField(
        LibraryEntry,
        on_delete=models.CASCADE,
        related_name="review",
        verbose_name="Книга",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Заголовок рецензії",
    )
    text = models.TextField(
        verbose_name="Текст рецензії",
    )
    contains_spoilers = models.BooleanField(
        default=False,
        verbose_name="Містить спойлери",
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name="Опублікована",
    )

    def __str__(self):
        return f"Рецензія: {self.library_entry.book.title}"

    class Meta:
        verbose_name = "Рецензія"
        verbose_name_plural = "Рецензії"


# ============================================================================
# СЕСІЇ ЧИТАННЯ
# ============================================================================

class ReadingSession(TimeStampedModel):
    """
    Дозволяє зберігати історію читання:
    коли користувач читав, скільки сторінок і скільки часу.
    """

    library_entry = models.ForeignKey(
        LibraryEntry,
        on_delete=models.CASCADE,
        related_name="reading_sessions",
        verbose_name="Книга",
    )
    started_at = models.DateTimeField(
        verbose_name="Початок читання",
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Завершення читання",
    )
    start_page = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Початкова сторінка",
    )
    end_page = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Кінцева сторінка",
    )
    note = models.TextField(
        blank=True,
        verbose_name="Коментар до сесії",
    )

    @property
    def pages_read(self):
        if self.start_page is None or self.end_page is None:
            return None

        return max(self.end_page - self.start_page, 0)

    @property
    def duration(self):
        if not self.finished_at:
            return None

        return self.finished_at - self.started_at

    def clean(self):
        errors = {}

        if self.finished_at and self.finished_at < self.started_at:
            errors["finished_at"] = (
                "Час завершення не може бути раніше часу початку."
            )

        if (
            self.start_page is not None
            and self.end_page is not None
            and self.end_page < self.start_page
        ):
            errors["end_page"] = (
                "Кінцева сторінка не може бути меншою за початкову."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.library_entry.book.title}: "
            f"{self.started_at:%d.%m.%Y %H:%M}"
        )

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Сесія читання"
        verbose_name_plural = "Сесії читання"
        indexes = [
            models.Index(fields=["library_entry", "-started_at"]),
        ]