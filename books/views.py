from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from django.contrib.auth.decorators import login_required
from asgiref.sync import sync_to_async
from .models import Book
from .forms import BookForm
# Для демонстрації та тестування, якщо користувач не авторизований,
# ми тимчасово опустимо декоратор @login_required або зробимо перевірку всередині,
# щоб проект можна було запустити миттєво.
async def book_main_page(request: HttpRequest) -> HttpResponse:
    search_query: str = request.GET.get('search', '').strip().lower()
    # Асинхронна фільтрація книг (пошук за назвою або автором)
    def get_filtered_books() -> list[Book]:
        # Якщо користувач не увійшов, показуємо всі книги (для спрощення першого запуску)
        if request.user.is_authenticated:
            queryset = Book.objects.filter(user=request.user)
        else:
            queryset = Book.objects.all()
        if search_query:
            from django.db.models import Q
            queryset = queryset.filter(Q(title__icontains=search_query) | Q(author__icontains=search_query))
        return list(queryset)
    books: list[Book] = await sync_to_async(get_filtered_books)()
    if request.method == 'POST':
        def handle_post() -> bool:
            form = BookForm(request.POST)
            if form.is_valid():
                book = form.save(commit=False)
                # Прив'язуємо користувача, якщо він авторизований (інакше беремо першого з бази або тимчасово None)
                if request.user.is_authenticated:
                    book.user = request.user
                else:
                    from django.contrib.auth.models import User
                    book.user = User.objects.first()
                book.save()
                return True
            return False
        success: bool = await sync_to_async(handle_post)()
        if success:
            return redirect('book_main_page')
        form = BookForm()
    else:
        form_init = sync_to_async(BookForm)
        form = await form_init()
    context: dict = {
        'books': books,
        'form': form,
        'search_query': search_query,
    }
    render_template = sync_to_async(render)
    return await render_template(request, 'books.html', context)