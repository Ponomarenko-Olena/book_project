from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from books.management.commands.seed_demo_data import (
    DEMO_EMAIL,
    DEMO_ISBN_PREFIX,
    DEMO_USERNAME,
    DISABLED_MESSAGE,
)
from books.models import (
    Author,
    Book,
    BookNote,
    Bookmark,
    Category,
    LibraryEntry,
    Quote,
    ReadingSession,
    Review,
    Shelf,
)


@override_settings(DEBUG=True)
class SeedDemoDataCommandTests(TestCase):
    def run_seed(self, **options):
        stdout = StringIO()
        call_command("seed_demo_data", stdout=stdout, **options)
        return stdout.getvalue()

    def demo_user(self):
        return get_user_model().objects.get(username=DEMO_USERNAME)

    def demo_counts(self):
        user = self.demo_user()
        return {
            "users": get_user_model().objects.filter(username=DEMO_USERNAME).count(),
            "authors": Author.objects.count(),
            "categories": Category.objects.count(),
            "books": Book.objects.filter(isbn13__startswith=DEMO_ISBN_PREFIX).count(),
            "entries": LibraryEntry.objects.filter(user=user).count(),
            "shelves": Shelf.objects.filter(user=user).count(),
            "notes": BookNote.objects.filter(library_entry__user=user).count(),
            "bookmarks": Bookmark.objects.filter(library_entry__user=user).count(),
            "quotes": Quote.objects.filter(library_entry__user=user).count(),
            "reviews": Review.objects.filter(library_entry__user=user).count(),
            "sessions": ReadingSession.objects.filter(library_entry__user=user).count(),
        }

    def test_command_creates_demo_user_books_and_library(self):
        output = self.run_seed()

        user = self.demo_user()

        self.assertEqual(user.email, DEMO_EMAIL)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("DemoBook123!"))
        self.assertEqual(user.profile.display_name, "Олена Книголюб")
        self.assertEqual(Book.objects.filter(isbn13__startswith=DEMO_ISBN_PREFIX).count(), 36)
        self.assertEqual(LibraryEntry.objects.filter(user=user).count(), 24)
        self.assertIn("Demo data created successfully.", output)

    def test_repeated_run_does_not_create_duplicates(self):
        self.run_seed()
        counts_before = self.demo_counts()

        self.run_seed()

        self.assertEqual(self.demo_counts(), counts_before)

    def test_reset_deletes_only_demo_data(self):
        user_model = get_user_model()
        real_user = user_model.objects.create_user("real_reader", email="real@example.com")
        real_author = Author.objects.create(name="Реальний тестовий автор")
        real_category = Category.objects.create(name="Реальна категорія")
        real_book = Book.objects.create(title="Реальна книга", isbn13="9781111111111", added_by=real_user)
        real_book.authors.add(real_author)
        real_book.categories.add(real_category)

        self.run_seed()
        self.run_seed(reset=True)

        self.assertEqual(user_model.objects.filter(username=DEMO_USERNAME).count(), 1)
        self.assertEqual(Book.objects.filter(isbn13__startswith=DEMO_ISBN_PREFIX).count(), 36)
        self.assertTrue(user_model.objects.filter(username="real_reader").exists())
        self.assertTrue(Book.objects.filter(isbn13="9781111111111").exists())
        self.assertTrue(Author.objects.filter(name="Реальний тестовий автор").exists())
        self.assertTrue(Category.objects.filter(name="Реальна категорія").exists())

    def test_debug_false_blocks_unless_forced(self):
        with override_settings(DEBUG=False):
            with self.assertRaisesMessage(CommandError, DISABLED_MESSAGE):
                self.run_seed()

        with override_settings(DEBUG=False):
            self.run_seed(force=True)

        self.assertTrue(get_user_model().objects.filter(username=DEMO_USERNAME).exists())

    def test_pages_do_not_exceed_book_pages(self):
        self.run_seed()

        for note in BookNote.objects.select_related("library_entry__book"):
            if note.page is not None:
                self.assertLessEqual(note.page, note.library_entry.book.pages)

        for bookmark in Bookmark.objects.select_related("library_entry__book"):
            if bookmark.page is not None:
                self.assertLessEqual(bookmark.page, bookmark.library_entry.book.pages)

        for quote in Quote.objects.select_related("library_entry__book"):
            if quote.page is not None:
                self.assertLessEqual(quote.page, quote.library_entry.book.pages)

        for session in ReadingSession.objects.select_related("library_entry__book"):
            self.assertLessEqual(session.start_page, session.library_entry.book.pages)
            self.assertLessEqual(session.end_page, session.library_entry.book.pages)
            self.assertGreaterEqual(session.end_page, session.start_page)

    def test_completed_books_have_logical_progress(self):
        self.run_seed()

        completed_entries = LibraryEntry.objects.filter(status=LibraryEntry.ReadingStatus.COMPLETED).select_related("book")

        self.assertGreater(completed_entries.count(), 0)

        for entry in completed_entries:
            self.assertEqual(entry.progress_percent, 100)
            self.assertEqual(entry.current_page, entry.book.pages)
            self.assertIsNotNone(entry.started_at)
            self.assertIsNotNone(entry.finished_at)
            self.assertLessEqual(entry.started_at, entry.finished_at)

    def test_public_shelves_only_include_public_entries(self):
        self.run_seed()

        public_shelves = Shelf.objects.filter(is_public=True).prefetch_related("books")

        self.assertGreater(public_shelves.count(), 0)

        for shelf in public_shelves:
            self.assertGreater(shelf.books.count(), 0)
            self.assertFalse(
                shelf.books.exclude(visibility=LibraryEntry.Visibility.PUBLIC).exists()
            )
