from django.urls import path
from . import views
urlpatterns = [
    path('', views.book_main_page, name='book_main_page'),
]