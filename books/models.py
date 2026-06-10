from django.db import models
from django.contrib.auth.models import User
class Book(models.Model):
    title = models.CharField(max_length=255, verbose_name="Назва книги")
    author = models.CharField(max_length=255, verbose_name="Автор")
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name="Рік видання")
    description = models.TextField(blank=True, verbose_name="Опис/Рецензія")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='books', verbose_name="Користувач")
    def __str__(self) -> str:
        return f"{self.title} — {self.author}"