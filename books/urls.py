"""
URL routes for the books application.

Route groups:
- authentication and profiles;
- public book catalogue;
- authors and categories;
- personal library;
- tags and shelves;
- notes, bookmarks and quotes;
- reviews;
- reading sessions.

The URL names match the names used by redirect() in views.py.
"""

from django.urls import path

from . import views


app_name = "books"


urlpatterns = [
    # -------------------------------------------------------------------------
    # Home, authentication and profiles
    # -------------------------------------------------------------------------
    path(
        "",
        views.book_list,
        name="book_main_page",
    ),
    path(
        "register/",
        views.register,
        name="register",
    ),
    path(
        "dashboard/",
        views.dashboard,
        name="dashboard",
    ),
    path(
        "profile/edit/",
        views.profile_edit,
        name="profile_edit",
    ),
    path(
        "users/<int:user_id>/",
        views.public_profile,
        name="public_profile",
    ),

    # -------------------------------------------------------------------------
    # Book catalogue
    # -------------------------------------------------------------------------
    path(
        "books/",
        views.book_list,
        name="book_list",
    ),
    path(
        "books/new/",
        views.book_create,
        name="book_create",
    ),
    path(
        "books/<int:pk>/",
        views.book_detail,
        name="book_detail",
    ),
    path(
        "books/<int:pk>/edit/",
        views.book_update,
        name="book_update",
    ),
    path(
        "books/<int:pk>/delete/",
        views.book_delete,
        name="book_delete",
    ),

    # -------------------------------------------------------------------------
    # Authors
    # -------------------------------------------------------------------------
    path(
        "authors/",
        views.author_list,
        name="author_list",
    ),
    path(
        "authors/new/",
        views.author_create,
        name="author_create",
    ),
    path(
        "authors/<int:pk>/",
        views.author_detail,
        name="author_detail",
    ),
    path(
        "authors/<int:pk>/edit/",
        views.author_update,
        name="author_update",
    ),
    path(
        "authors/<int:pk>/delete/",
        views.author_delete,
        name="author_delete",
    ),

    # -------------------------------------------------------------------------
    # Categories
    # -------------------------------------------------------------------------
    path(
        "categories/",
        views.category_list,
        name="category_list",
    ),
    path(
        "categories/new/",
        views.category_create,
        name="category_create",
    ),
    path(
        "categories/<int:pk>/",
        views.category_detail,
        name="category_detail",
    ),
    path(
        "categories/<int:pk>/edit/",
        views.category_update,
        name="category_update",
    ),
    path(
        "categories/<int:pk>/delete/",
        views.category_delete,
        name="category_delete",
    ),

    # -------------------------------------------------------------------------
    # Personal library
    # -------------------------------------------------------------------------
    path(
        "library/",
        views.library_list,
        name="library_list",
    ),
    path(
        "library/add/",
        views.library_create,
        name="library_create",
    ),
    path(
        "books/<int:book_id>/add-to-library/",
        views.library_create,
        name="library_create_for_book",
    ),
    path(
        "library/<int:pk>/",
        views.library_detail,
        name="library_detail",
    ),
    path(
        "library/<int:pk>/edit/",
        views.library_update,
        name="library_update",
    ),
    path(
        "library/<int:pk>/delete/",
        views.library_delete,
        name="library_delete",
    ),
    path(
        "library/<int:pk>/toggle-favorite/",
        views.library_toggle_favorite,
        name="library_toggle_favorite",
    ),
    path(
        "library/<int:pk>/mark-completed/",
        views.library_mark_completed,
        name="library_mark_completed",
    ),
    path(
        "library/<int:pk>/set-progress/",
        views.library_set_progress,
        name="library_set_progress",
    ),

    # -------------------------------------------------------------------------
    # Personal tags
    # -------------------------------------------------------------------------
    path(
        "tags/",
        views.tag_list,
        name="tag_list",
    ),
    path(
        "tags/new/",
        views.tag_create,
        name="tag_create",
    ),
    path(
        "tags/<int:pk>/",
        views.tag_detail,
        name="tag_detail",
    ),
    path(
        "tags/<int:pk>/edit/",
        views.tag_update,
        name="tag_update",
    ),
    path(
        "tags/<int:pk>/delete/",
        views.tag_delete,
        name="tag_delete",
    ),

    # -------------------------------------------------------------------------
    # Private shelves
    # -------------------------------------------------------------------------
    path(
        "shelves/",
        views.shelf_list,
        name="shelf_list",
    ),
    path(
        "shelves/new/",
        views.shelf_create,
        name="shelf_create",
    ),
    path(
        "shelves/<int:pk>/",
        views.shelf_detail,
        name="shelf_detail",
    ),
    path(
        "shelves/<int:pk>/edit/",
        views.shelf_update,
        name="shelf_update",
    ),
    path(
        "shelves/<int:pk>/delete/",
        views.shelf_delete,
        name="shelf_delete",
    ),
    path(
        "shelves/<int:pk>/books/<int:entry_id>/add/",
        views.shelf_add_book,
        name="shelf_add_book",
    ),
    path(
        "shelves/<int:pk>/books/<int:entry_id>/remove/",
        views.shelf_remove_book,
        name="shelf_remove_book",
    ),

    # -------------------------------------------------------------------------
    # Public shelves
    # -------------------------------------------------------------------------
    path(
        "public/shelves/",
        views.public_shelf_list,
        name="public_shelf_list",
    ),
    path(
        "public/shelves/<int:pk>/",
        views.public_shelf_detail,
        name="public_shelf_detail",
    ),

    # -------------------------------------------------------------------------
    # Book notes
    # -------------------------------------------------------------------------
    path(
        "notes/",
        views.note_list,
        name="note_list",
    ),
    path(
        "notes/new/",
        views.note_create,
        name="note_create",
    ),
    path(
        "library/<int:entry_id>/notes/new/",
        views.note_create,
        name="note_create_for_entry",
    ),
    path(
        "notes/<int:pk>/",
        views.note_detail,
        name="note_detail",
    ),
    path(
        "notes/<int:pk>/edit/",
        views.note_update,
        name="note_update",
    ),
    path(
        "notes/<int:pk>/delete/",
        views.note_delete,
        name="note_delete",
    ),
    path(
        "notes/<int:pk>/toggle-pin/",
        views.note_toggle_pin,
        name="note_toggle_pin",
    ),

    # -------------------------------------------------------------------------
    # Bookmarks
    # -------------------------------------------------------------------------
    path(
        "bookmarks/",
        views.bookmark_list,
        name="bookmark_list",
    ),
    path(
        "bookmarks/new/",
        views.bookmark_create,
        name="bookmark_create",
    ),
    path(
        "library/<int:entry_id>/bookmarks/new/",
        views.bookmark_create,
        name="bookmark_create_for_entry",
    ),
    path(
        "bookmarks/<int:pk>/",
        views.bookmark_detail,
        name="bookmark_detail",
    ),
    path(
        "bookmarks/<int:pk>/edit/",
        views.bookmark_update,
        name="bookmark_update",
    ),
    path(
        "bookmarks/<int:pk>/delete/",
        views.bookmark_delete,
        name="bookmark_delete",
    ),

    # -------------------------------------------------------------------------
    # Quotes
    # -------------------------------------------------------------------------
    path(
        "quotes/",
        views.quote_list,
        name="quote_list",
    ),
    path(
        "quotes/new/",
        views.quote_create,
        name="quote_create",
    ),
    path(
        "library/<int:entry_id>/quotes/new/",
        views.quote_create,
        name="quote_create_for_entry",
    ),
    path(
        "quotes/<int:pk>/",
        views.quote_detail,
        name="quote_detail",
    ),
    path(
        "quotes/<int:pk>/edit/",
        views.quote_update,
        name="quote_update",
    ),
    path(
        "quotes/<int:pk>/delete/",
        views.quote_delete,
        name="quote_delete",
    ),
    path(
        "quotes/<int:pk>/toggle-favorite/",
        views.quote_toggle_favorite,
        name="quote_toggle_favorite",
    ),

    # -------------------------------------------------------------------------
    # Private reviews
    # -------------------------------------------------------------------------
    path(
        "reviews/",
        views.review_list,
        name="review_list",
    ),
    path(
        "reviews/new/",
        views.review_create,
        name="review_create",
    ),
    path(
        "library/<int:entry_id>/reviews/new/",
        views.review_create,
        name="review_create_for_entry",
    ),
    path(
        "reviews/<int:pk>/",
        views.review_detail,
        name="review_detail",
    ),
    path(
        "reviews/<int:pk>/edit/",
        views.review_update,
        name="review_update",
    ),
    path(
        "reviews/<int:pk>/delete/",
        views.review_delete,
        name="review_delete",
    ),
    path(
        "reviews/<int:pk>/toggle-publication/",
        views.review_toggle_publication,
        name="review_toggle_publication",
    ),

    # -------------------------------------------------------------------------
    # Public reviews
    # -------------------------------------------------------------------------
    path(
        "public/reviews/",
        views.public_review_list,
        name="public_review_list",
    ),
    path(
        "public/reviews/<int:pk>/",
        views.public_review_detail,
        name="public_review_detail",
    ),

    # -------------------------------------------------------------------------
    # Reading sessions
    # -------------------------------------------------------------------------
    path(
        "reading-sessions/",
        views.reading_session_list,
        name="reading_session_list",
    ),
    path(
        "reading-sessions/new/",
        views.reading_session_create,
        name="reading_session_create",
    ),
    path(
        "library/<int:entry_id>/reading-sessions/new/",
        views.reading_session_create,
        name="reading_session_create_for_entry",
    ),
    path(
        "reading-sessions/<int:pk>/",
        views.reading_session_detail,
        name="reading_session_detail",
    ),
    path(
        "reading-sessions/<int:pk>/edit/",
        views.reading_session_update,
        name="reading_session_update",
    ),
    path(
        "reading-sessions/<int:pk>/delete/",
        views.reading_session_delete,
        name="reading_session_delete",
    ),

    # -------------------------------------------------------------------------
    # Temporary compatibility aliases for older templates
    # -------------------------------------------------------------------------
    path(
        "books/",
        views.book_list,
        name="books_list",
    ),
    path(
        "books/new/",
        views.book_create,
        name="books_create",
    ),
    path(
        "books/<int:pk>/",
        views.book_detail,
        name="books_detail",
    ),
    path(
        "books/<int:pk>/edit/",
        views.book_update,
        name="books_edit",
    ),
    path(
        "books/<int:pk>/delete/",
        views.book_delete,
        name="books_delete",
    ),
]
