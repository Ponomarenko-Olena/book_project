from django import forms
from .models import Book
class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ['title', 'author', 'year', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 text-sm p-2.5 border', 'placeholder': 'Назва книги...'}),
            'author': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 text-sm p-2.5 border', 'placeholder': 'Імʼя автора...'}),
            'year': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 text-sm p-2.5 border', 'placeholder': 'Рік...'}),
            'description': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 text-sm p-2.5 border', 'rows': 3, 'placeholder': 'Ваш відгук...'}),
        }