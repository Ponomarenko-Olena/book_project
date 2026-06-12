from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from books import services
from books.models import (
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
)


DEMO_USERNAME = "demo_reader"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "DemoBook123!"
DEMO_ISBN_PREFIX = "97800000"
DISABLED_MESSAGE = "Demo data seeding is disabled when DEBUG=False."


AUTHOR_DATA = [
    ("Марія Вітрова", "Пише камерне фентезі про міста, пам'ять і вибір. У минулому працювала редакторкою дитячих журналів."),
    ("Олександр Левицький", "Вигаданий автор технічної прози та пригодницьких романів про людей, які шукають порядок у хаосі."),
    ("Софія Ясна", "Створює сучасну прозу з теплим гумором, уважністю до деталей і сильними жіночими голосами."),
    ("Андрій Черненко", "Автор детективів із повільним розслідуванням, міськими легендами та чесними моральними дилемами."),
    ("Ірина Морська", "Пише науково-популярні книги про біологію, екологію та повсякденні наукові спостереження."),
    ("Тарас Зоряний", "Фантаст, який вигадує зоряні поштові маршрути, далекі колонії та побут майбутнього."),
    ("Наталія Берегова", "Авторка психологічних есеїв про рішення, звички й уважне ставлення до власного часу."),
    ("Максим Коваль", "Вигаданий інженер-практик, який пояснює Python, Django, Linux і DevOps людською мовою."),
    ("Леся Гринь", "Пише дитячі пригоди, коміксні історії та тексти для сімейного читання."),
    ("Владислав Орест", "Автор історичних романів і нарисів про міста, які зберігають пам'ять у двориках та архівах."),
    ("Катерина Ланова", "Створює романтичну прозу про дорослі розмови, дороги, каву та другий шанс."),
    ("Денис Сніговий", "Пише про філософію повсякденності, етику малих вчинків і тихі ранкові маршрути."),
    ("Олена Руда", "Авторка арт-есеїв і книг про книжкову культуру, палітурки, майстерні та домашні бібліотеки."),
    ("Павло Вербовий", "Популяризатор науки у вигаданому університеті; любить фізику, математику й несподівані приклади."),
    ("Христина Далека", "Пише підліткову фантастику й пригоди з мапами, маяками та дружбою, яка витримує дорогу."),
]


CATEGORY_DATA = [
    ("Художня література", None, "Романи, оповіді та сюжетна проза для різного настрою."),
    ("Фентезі", "Художня література", "Магічні світи, квести та легенди."),
    ("Наукова фантастика", "Художня література", "Майбутнє, космос і технології."),
    ("Детектив", "Художня література", "Розслідування, таємниці та міські загадки."),
    ("Пригоди", "Художня література", "Подорожі, ризик і відкриття."),
    ("Роман", "Художня література", "Сучасна й романтична проза."),
    ("Історична проза", "Художня література", "Минуле, архіви та вигадані долі."),
    ("Нехудожня література", None, "Практичні, пізнавальні та аналітичні книги."),
    ("Психологія", "Нехудожня література", "Рішення, звички та поведінка."),
    ("Програмування", "Нехудожня література", "Технічні книги для розробників."),
    ("Python", "Програмування", "Python для навчання і роботи."),
    ("Django", "Програмування", "Веброзробка на Django."),
    ("Linux", "Програмування", "Системне середовище розробника."),
    ("DevOps", "Програмування", "Контейнери, хмари й автоматизація."),
    ("Історія", "Нехудожня література", "Міста, події та культурна пам'ять."),
    ("Наука", "Нехудожня література", "Популярна наука для щоденного читання."),
    ("Саморозвиток", "Нехудожня література", "Практики навчання і професійного росту."),
    ("Філософія", "Нехудожня література", "Ідеї, етика та спостереження."),
    ("Мистецтво", "Нехудожня література", "Візуальна культура і книжковий дизайн."),
    ("Дитяча література", None, "Книжки для дітей і сімейного читання."),
    ("Казки", "Дитяча література", "Добрі історії й фантастичні пригоди."),
    ("Підліткова проза", "Дитяча література", "Історії дорослішання і дружби."),
    ("Комікси", "Дитяча література", "Мальовані пригоди й легке читання."),
]


BOOK_DATA = [
    ("Тіні над Арденом", "Літопис прикордонного міста", "Марія Вітрова", ["Фентезі"], 2021, 384, "Видавництво Північ", "Арденські хроніки", Decimal("1.0")),
    ("Сьомий ключ Асторії", "Роман про двері, що пам'ятають голоси", "Марія Вітрова", ["Фентезі"], 2022, 416, "Видавництво Північ", "Арденські хроніки", Decimal("2.0")),
    ("Хроніки Срібного Лісу", "Пісні старих дерев", "Христина Далека", ["Фентезі", "Підліткова проза"], 2020, 352, "Лісова майстерня", "Срібний ліс", Decimal("1.0")),
    ("Місто під двома місяцями", "Космічний роман", "Тарас Зоряний", ["Наукова фантастика"], 2023, 448, "Орбіта", "", None),
    ("Останній картограф", "Пригода на краю відомого світу", "Олександр Левицький", ["Пригоди", "Наукова фантастика"], 2019, 368, "Компас", "", None),
    ("Дім, де сплять годинники", "Сучасна проза", "Софія Ясна", ["Роман"], 2024, 288, "Теплий том", "", None),
    ("Кава після дощу", "Роман про другі шанси", "Катерина Ланова", ["Роман"], 2021, 304, "Теплий том", "", None),
    ("Нічний архіваріус", "Детектив із закритого фонду", "Андрій Черненко", ["Детектив"], 2022, 336, "Чорнильна справа", "Архіваріус", Decimal("1.0")),
    ("Справа тихої набережної", "Міський детектив", "Андрій Черненко", ["Детектив"], 2024, 320, "Чорнильна справа", "Архіваріус", Decimal("2.0")),
    ("Психологія щоденних рішень", "Як не губитися в малому", "Наталія Берегова", ["Психологія", "Саморозвиток"], 2023, 272, "Практика", "", None),
    ("Алгоритми спокою", "Поведінкові нотатки для напружених тижнів", "Наталія Берегова", ["Психологія", "Саморозвиток"], 2025, 248, "Практика", "", None),
    ("Python без страху", "Перші програми без зайвої магії", "Максим Коваль", ["Python", "Програмування"], 2024, 412, "Код і кава", "", None),
    ("Django: шлях від моделі до сервера", "Практичний вебкурс", "Максим Коваль", ["Django", "Програмування"], 2025, 456, "Код і кава", "", None),
    ("Linux для веброзробника", "Термінал, процеси, деплой", "Максим Коваль", ["Linux", "Програмування"], 2023, 340, "Код і кава", "", None),
    ("Контейнери та хмари", "DevOps без паніки", "Максим Коваль", ["DevOps", "Програмування"], 2025, 376, "Код і кава", "", None),
    ("Історія забутих міст", "Нариси про місця, яких немає на мапах", "Владислав Орест", ["Історія"], 2020, 292, "Архів", "", None),
    ("Десять листів із Подолу", "Історична проза", "Владислав Орест", ["Історична проза"], 2022, 328, "Архів", "", None),
    ("Наука поруч", "Досліди для уважного дня", "Ірина Морська", ["Наука"], 2024, 236, "Лабораторія слова", "", None),
    ("Біологія міського саду", "Живі системи між будинками", "Ірина Морська", ["Наука"], 2021, 264, "Лабораторія слова", "", None),
    ("Фізика повсякденних див", "Чому речі поводяться саме так", "Павло Вербовий", ["Наука"], 2022, 280, "Лабораторія слова", "", None),
    ("Географія у рюкзаку", "Малі подорожі великим світом", "Христина Далека", ["Пригоди", "Наука"], 2020, 224, "Компас", "", None),
    ("Математика для допитливих", "Задачі, що розповідають історії", "Павло Вербовий", ["Наука"], 2023, 256, "Лабораторія слова", "", None),
    ("Англійська без паніки", "Мова для читачів і розробників", "Софія Ясна", ["Саморозвиток"], 2024, 300, "Практика", "", None),
    ("Комікс-клуб на горищі", "Мальована пригода", "Леся Гринь", ["Комікси", "Дитяча література"], 2022, 168, "Веселі сторінки", "", None),
    ("Капітан і зоряний пил", "Казка про сміливість", "Леся Гринь", ["Казки", "Пригоди"], 2021, 144, "Веселі сторінки", "", None),
    ("Етика маленьких рішень", "Філософія на щодень", "Денис Сніговий", ["Філософія", "Саморозвиток"], 2025, 232, "Практика", "", None),
    ("Філософія ранкових прогулянок", "Повільні есеї", "Денис Сніговий", ["Філософія"], 2020, 216, "Тихий берег", "", None),
    ("Візерунки старої палітурки", "Есеї про книжкове мистецтво", "Олена Руда", ["Мистецтво", "Історія"], 2023, 240, "Майстерня", "", None),
    ("Книга про книжкову шафу", "Як речі стають пам'яттю", "Олена Руда", ["Роман", "Мистецтво"], 2024, 276, "Майстерня", "", None),
    ("Любов на сьомій платформі", "Роман у дорозі", "Катерина Ланова", ["Роман"], 2022, 312, "Теплий том", "", None),
    ("Листи до майбутньої себе", "Проза про навчання жити", "Софія Ясна", ["Роман", "Саморозвиток"], 2025, 260, "Теплий том", "", None),
    ("Космічна пошта", "Підліткова фантастика", "Тарас Зоряний", ["Наукова фантастика", "Підліткова проза"], 2021, 304, "Орбіта", "", None),
    ("Детектив без парасолі", "Сімейна таємниця у дощовому місті", "Леся Гринь", ["Детектив", "Підліткова проза"], 2023, 240, "Веселі сторінки", "", None),
    ("Щоденник молодого DevOps", "Нотатки з першого релізу", "Олександр Левицький", ["DevOps", "Програмування"], 2026, 288, "Код і кава", "", None),
    ("Архітектура тихого коду", "Як думати про підтримувані системи", "Максим Коваль", ["Програмування"], 2026, 360, "Код і кава", "", None),
    ("Мандрівка до синього маяка", "Пригода про дружбу і карту", "Христина Далека", ["Пригоди", "Підліткова проза"], 2022, 272, "Компас", "", None),
]


TAG_DATA = [
    ("Для роботи", "#4dabf7"),
    ("На вихідні", "#ffd43b"),
    ("Перечитати", "#b197fc"),
    ("Улюблене", "#ff6b6b"),
    ("Складне", "#868e96"),
    ("Легке читання", "#69db7c"),
    ("Навчання", "#38d9a9"),
    ("Подарунок", "#ffa94d"),
    ("Українською", "#74c0fc"),
]


NOTE_BODIES = [
    "Основна ідея розділу добре працює як нагадування: рухатися малими, але регулярними кроками.",
    "Повернутися до цього пояснення перед наступним плануванням, бо тут є практичний приклад.",
    "Цікавий образ міста: воно поводиться майже як окремий герой і змінює темп історії.",
    "Важливе правило для практики: спочатку зрозуміти контекст, потім обирати інструмент.",
    "Порівняти з іншою книгою на цю тему, особливо щодо структури аргументів.",
    "Гарний фрагмент для обговорення у книжковому клубі, бо він має кілька прочитань.",
]


QUOTE_TEXTS = [
    "Карта показує шлях лише тому, хто вже наважився рушити.",
    "Найскладніший алгоритм починається з простого запитання.",
    "Пам'ять міста живе у тих, хто ще слухає його тишу.",
    "Добра звичка не шумить, але щодня пересуває межу можливого.",
    "Коли світло згасає, книжкова шафа все одно тримає форму кімнати.",
    "Сміливість інколи виглядає як записаний план на завтра.",
    "Зорі не дають відповідей, зате вчать дивитися далі.",
    "Код стає спокійним, коли люди домовляються про сенс.",
    "Кожна закладка є маленькою обіцянкою повернутися.",
    "Мандрівка починається там, де карта перестає вдавати певність.",
    "Тиша архіву була гучнішою за будь-яке зізнання.",
    "Найкращі рішення часто народжуються після паузи, а не після поспіху.",
    "Дощ навчив місто говорити короткими реченнями.",
    "Книга не зберігає час, вона дає йому нову форму.",
    "Пояснення стає чесним, коли витримує приклад.",
    "Маленьке відкриття інколи тримає цілий день на плаву.",
    "Дружба схожа на маяк: вона не скорочує шлях, але не дає збитися.",
    "У кожній старій палітурці є слід рук, які вірили тексту.",
    "Питання, поставлене вчасно, економить сторінки сумнівів.",
    "Дорога не питає, чи готовий ти, вона просто відкриває наступний поворот.",
]


class Command(BaseCommand):
    help = "Seeds realistic local demo data for the book library project."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete only this command's demo data before seeding.")
        parser.add_argument("--force", action="store_true", help="Allow seeding when DEBUG=False.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(DISABLED_MESSAGE)

        with transaction.atomic():
            if options["reset"]:
                self.stdout.write(self.style.WARNING("Resetting demo data..."))
                self._reset_demo_data()

            user = self._create_user()
            authors = self._create_authors()
            categories = self._create_categories()
            books = self._create_books(user, authors, categories)
            tags = self._create_tags(user)
            entries = self._create_library_entries(user, books, tags)
            self._create_shelves(user, entries)
            self._create_notes(user, entries)
            self._create_bookmarks(user, entries)
            self._create_quotes(user, entries)
            self._create_reviews(user, entries)
            self._create_reading_sessions(user, entries)
            summary = self._summary(user)

        self.stdout.write(self.style.SUCCESS("Demo data created successfully."))
        self.stdout.write("Local DEBUG credentials only. Do not use these credentials in production.")

        for label, count in summary.items():
            self.stdout.write(f"{label}: {count}")

    def _reset_demo_data(self):
        user_model = get_user_model()
        user_model.objects.filter(username=DEMO_USERNAME, email=DEMO_EMAIL).delete()
        Book.objects.filter(isbn13__startswith=DEMO_ISBN_PREFIX).delete()
        Author.objects.filter(name__in=[name for name, _ in AUTHOR_DATA]).delete()
        Category.objects.filter(name__in=[name for name, _, _ in CATEGORY_DATA]).delete()

    def _create_user(self):
        self.stdout.write("Creating demo user...")
        user_model = get_user_model()
        user, _ = user_model.objects.update_or_create(
            username=DEMO_USERNAME,
            defaults={
                "email": DEMO_EMAIL,
                "first_name": "Олена",
                "last_name": "Книголюб",
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )
        user.set_password(DEMO_PASSWORD)
        user.save()

        self.stdout.write("Creating profile...")
        services.create_or_update_user_profile(
            user=user,
            display_name="Олена Книголюб",
            timezone="Europe/Kyiv",
            bio="Читаю фентезі, наукову фантастику, психологію та сучасну українську прозу.",
        )
        return user

    def _create_authors(self):
        self.stdout.write("Creating authors...")
        authors = {}

        for name, biography in AUTHOR_DATA:
            author, _ = Author.objects.update_or_create(
                name=name,
                defaults={"biography": biography, "website": ""},
            )
            author.full_clean()
            author.save()
            authors[name] = author

        return authors

    def _create_categories(self):
        self.stdout.write("Creating categories...")
        categories = {}

        for index, (name, parent_name, description) in enumerate(CATEGORY_DATA, start=1):
            parent = categories.get(parent_name)
            category, _ = Category.objects.update_or_create(
                name=name,
                defaults={
                    "parent": parent,
                    "description": description,
                    "slug": f"demo-category-{index:02d}",
                },
            )
            category.full_clean()
            category.save()
            categories[name] = category

        return categories

    def _create_books(self, user, authors, categories):
        self.stdout.write("Creating books...")
        books = {}

        for index, (title, subtitle, author_name, category_names, year, pages, publisher, series_name, series_number) in enumerate(BOOK_DATA, start=1):
            isbn13 = f"{DEMO_ISBN_PREFIX}{index:05d}"
            book, _ = Book.objects.update_or_create(
                isbn13=isbn13,
                defaults={
                    "title": title,
                    "subtitle": subtitle,
                    "publisher": publisher,
                    "published_year": year,
                    "pages": pages,
                    "language": "Українська",
                    "description": (
                        f"Демонстраційна вигадана книга «{title}». "
                        f"Вона показує, як виглядає каталог із реалістичними описами, категоріями та різними обкладинками."
                    ),
                    "cover_url": "",
                    "series_name": series_name,
                    "series_number": series_number,
                    "added_by": user,
                },
            )
            book.authors.set([authors[author_name]])
            book.categories.set([categories[name] for name in category_names])
            book.full_clean()
            book.save()
            books[title] = book

        return books

    def _create_tags(self, user):
        self.stdout.write("Creating tags...")
        tags = {}

        for name, color in TAG_DATA:
            tag, _ = PersonalTag.objects.update_or_create(
                user=user,
                name=name,
                defaults={"color": color},
            )
            tag.full_clean()
            tag.save()
            tags[name] = tag

        return tags

    def _create_library_entries(self, user, books, tags):
        self.stdout.write("Creating library entries...")
        today = timezone.localdate()
        status_plan = (
            [LibraryEntry.ReadingStatus.READING] * 5
            + [LibraryEntry.ReadingStatus.PAUSED] * 2
            + [LibraryEntry.ReadingStatus.COMPLETED] * 9
            + [LibraryEntry.ReadingStatus.DROPPED] * 2
            + [LibraryEntry.ReadingStatus.WANT_TO_READ] * 6
        )
        formats = [
            LibraryEntry.BookFormat.PAPER,
            LibraryEntry.BookFormat.EBOOK,
            LibraryEntry.BookFormat.AUDIOBOOK,
            LibraryEntry.BookFormat.PAPER,
        ]
        tag_names = list(tags)
        entries = {}

        for index, title in enumerate(list(books)[:24]):
            book = books[title]
            status = status_plan[index]
            pages = book.pages or 240
            current_page = 0
            rating = None
            started_at = None
            finished_at = None

            if status == LibraryEntry.ReadingStatus.READING:
                current_page = min(pages - 25, 60 + index * 19)
                started_at = today - timedelta(days=10 + index * 3)
            elif status == LibraryEntry.ReadingStatus.PAUSED:
                current_page = min(pages - 20, pages // 3)
                started_at = today - timedelta(days=31 + index)
            elif status == LibraryEntry.ReadingStatus.COMPLETED:
                current_page = pages
                rating = 4 + (index % 2)
                started_at = today - timedelta(days=58 - index)
                finished_at = today - timedelta(days=24 - (index % 12))
            elif status == LibraryEntry.ReadingStatus.DROPPED:
                current_page = max(20, pages // 5)
                started_at = today - timedelta(days=42 - index)

            visibility = (
                LibraryEntry.Visibility.PUBLIC
                if index < 16
                else (
                    LibraryEntry.Visibility.FRIENDS
                    if index % 2
                    else LibraryEntry.Visibility.PRIVATE
                )
            )

            entry, _ = LibraryEntry.objects.update_or_create(
                user=user,
                book=book,
                defaults={
                    "status": status,
                    "book_format": formats[index % len(formats)],
                    "visibility": visibility,
                    "current_page": current_page,
                    "rating": rating,
                    "is_favorite": index in {0, 1, 2, 7, 10, 12, 17},
                    "is_owned": index % 5 != 0,
                    "started_at": started_at,
                    "finished_at": finished_at,
                },
            )

            if entry.status == LibraryEntry.ReadingStatus.COMPLETED:
                entry.current_page = pages
                entry.progress_percent = 100
            else:
                entry.update_progress_from_page()

            entry.full_clean()
            entry.save()

            selected_tags = [
                tags[tag_names[index % len(tag_names)]],
                tags[tag_names[(index + 3) % len(tag_names)]],
            ]
            entry.tags.set(selected_tags)
            entries[title] = entry

        return entries

    def _create_shelves(self, user, entries):
        self.stdout.write("Creating shelves...")
        public_entries = {
            title: entry
            for title, entry in entries.items()
            if entry.visibility == LibraryEntry.Visibility.PUBLIC
        }
        shelf_data = [
            ("Зараз читаю", False, ["Тіні над Арденом", "Сьомий ключ Асторії", "Хроніки Срібного Лісу", "Місто під двома місяцями"]),
            ("Улюблене фентезі", True, ["Тіні над Арденом", "Сьомий ключ Асторії", "Хроніки Срібного Лісу"]),
            ("Python і Django", True, ["Python без страху", "Django: шлях від моделі до сервера", "Linux для веброзробника"]),
            ("Для професійного розвитку", False, ["Python без страху", "Django: шлях від моделі до сервера", "Linux для веброзробника", "Контейнери та хмари"]),
            ("Легке читання", False, ["Кава після дощу", "Комікс-клуб на горищі", "Капітан і зоряний пил"]),
            ("Прочитано у 2026 році", True, ["Нічний архіваріус", "Справа тихої набережної", "Психологія щоденних рішень", "Алгоритми спокою"]),
            ("Наступні до читання", False, ["Наука поруч", "Біологія міського саду", "Фізика повсякденних див", "Географія у рюкзаку"]),
        ]

        for name, is_public, titles in shelf_data:
            shelf, _ = Shelf.objects.update_or_create(
                user=user,
                name=name,
                defaults={
                    "description": f"Демонстраційна полиця «{name}» з підібраними книгами.",
                    "is_public": is_public,
                },
            )
            source = public_entries if is_public else entries
            shelf.books.set([source[title] for title in titles if title in source])
            shelf.full_clean()
            shelf.save()

    def _create_notes(self, user, entries):
        self.stdout.write("Creating notes...")
        note_types = [
            BookNote.NoteType.NOTE,
            BookNote.NoteType.SUMMARY,
            BookNote.NoteType.IDEA,
            BookNote.NoteType.QUESTION,
            BookNote.NoteType.TODO,
        ]

        for index, entry in enumerate(list(entries.values())[:24], start=1):
            page = self._safe_page(entry, fallback=index * 11)
            note, _ = BookNote.objects.update_or_create(
                library_entry=entry,
                title=f"Демо-нотатка {index}",
                defaults={
                    "note_type": note_types[index % len(note_types)],
                    "body": NOTE_BODIES[index % len(NOTE_BODIES)],
                    "page": page,
                    "is_pinned": index in {1, 5, 12, 19},
                },
            )
            note.full_clean()
            note.save()

    def _create_bookmarks(self, user, entries):
        self.stdout.write("Creating bookmarks...")

        for index, entry in enumerate(list(entries.values())[:18], start=1):
            use_position = entry.book_format == LibraryEntry.BookFormat.AUDIOBOOK
            page = None if use_position else self._safe_page(entry, fallback=index * 13)
            position = f"0{index % 3}:2{index % 6}:30" if use_position else ""
            bookmark, _ = Bookmark.objects.update_or_create(
                library_entry=entry,
                label=f"Демо-закладка {index}",
                defaults={
                    "page": page,
                    "position": position,
                    "comment": "Місце, до якого варто повернутися під час повторного читання.",
                },
            )
            bookmark.full_clean()
            bookmark.save()

    def _create_quotes(self, user, entries):
        self.stdout.write("Creating quotes...")

        for index, text in enumerate(QUOTE_TEXTS, start=1):
            entry = list(entries.values())[(index - 1) % len(entries)]
            quote, _ = Quote.objects.update_or_create(
                library_entry=entry,
                text=text,
                defaults={
                    "page": self._safe_page(entry, fallback=index * 9),
                    "comment": "Оригінальна коротка цитата для демонстраційних даних.",
                    "is_favorite": index in {1, 2, 5, 8, 13},
                },
            )
            quote.full_clean()
            quote.save()

    def _create_reviews(self, user, entries):
        self.stdout.write("Creating reviews...")
        review_texts = [
            "Сильна атмосферна книга з виразним темпом і дуже вдалим фіналом.",
            "Практична користь очевидна: після кожного розділу хочеться щось застосувати.",
            "Не все спрацювало рівно, але стиль і герої тримають увагу.",
            "Добрий баланс між емоційністю та структурою, особливо для вечірнього читання.",
            "Книжка корисна як вступ до теми, хоча окремі місця хотілося б розгорнути.",
            "Професійний, стриманий текст із прикладами, які легко перенести у роботу.",
            "Сюжет неквапний, зате дуже точний у деталях і настрої.",
            "Найкраще працюють діалоги та сцени, де герої ухвалюють складні рішення.",
            "Чернеткова думка: треба перечитати кілька розділів перед остаточною оцінкою.",
            "Емоційна історія з кількома несподіваними поворотами і теплим післясмаком.",
        ]

        for index, entry in enumerate(list(entries.values())[:10], start=1):
            review, _ = Review.objects.update_or_create(
                library_entry=entry,
                defaults={
                    "title": f"Враження після читання {index}",
                    "text": review_texts[index - 1],
                    "contains_spoilers": index in {3, 7},
                    "is_published": index <= 7,
                },
            )
            review.full_clean()
            review.save()

    def _create_reading_sessions(self, user, entries):
        self.stdout.write("Creating reading sessions...")
        eligible_entries = [
            entry
            for entry in entries.values()
            if entry.status in {
                LibraryEntry.ReadingStatus.READING,
                LibraryEntry.ReadingStatus.COMPLETED,
                LibraryEntry.ReadingStatus.PAUSED,
            }
        ]
        base_date = timezone.localdate()

        for index in range(42):
            entry = eligible_entries[index % len(eligible_entries)]
            pages = entry.book.pages or 240
            pages_read = 5 + ((index * 7) % 36)
            max_start = max(1, pages - pages_read - 1)
            start_page = 1 + ((index * 17) % max_start)
            end_page = min(pages, start_page + pages_read)
            started_date = base_date - timedelta(days=1 + ((index * 3) % 58))
            started_time = time(hour=7 + (index % 12), minute=(index * 7) % 60)
            started_at = timezone.make_aware(datetime.combine(started_date, started_time))
            finished_at = started_at + timedelta(minutes=20 + ((index * 9) % 95))

            session, _ = ReadingSession.objects.update_or_create(
                library_entry=entry,
                started_at=started_at,
                defaults={
                    "finished_at": finished_at,
                    "start_page": start_page,
                    "end_page": end_page,
                    "note": f"Демо-сесія читання {index + 1}: стабільний прогрес без поспіху.",
                },
            )
            session.full_clean()
            session.save()

    def _safe_page(self, entry, fallback):
        pages = entry.book.pages or 200
        if entry.current_page:
            return max(1, min(entry.current_page, pages))
        return max(1, min(fallback, pages))

    def _summary(self, user):
        demo_entries = LibraryEntry.objects.filter(user=user)

        return {
            "Users": 1,
            "Authors": Author.objects.filter(name__in=[name for name, _ in AUTHOR_DATA]).count(),
            "Categories": Category.objects.filter(name__in=[name for name, _, _ in CATEGORY_DATA]).count(),
            "Books": Book.objects.filter(isbn13__startswith=DEMO_ISBN_PREFIX).count(),
            "Library entries": demo_entries.count(),
            "Shelves": Shelf.objects.filter(user=user).count(),
            "Tags": PersonalTag.objects.filter(user=user).count(),
            "Notes": BookNote.objects.filter(library_entry__user=user).count(),
            "Bookmarks": Bookmark.objects.filter(library_entry__user=user).count(),
            "Quotes": Quote.objects.filter(library_entry__user=user).count(),
            "Reviews": Review.objects.filter(library_entry__user=user).count(),
            "Reading sessions": ReadingSession.objects.filter(library_entry__user=user).count(),
        }
