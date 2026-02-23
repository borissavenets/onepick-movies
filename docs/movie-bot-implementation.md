# 🎬 Лендінг для Telegram-бота підбору фільмів
## Імплементаційний план для Claude Code

---

# СТРУКТУРА ПРОЄКТУ

```
/movie-bot-landing
├── index.html          # Лендінг (one-page)
├── styles.css          # Стилі (mobile-first)
├── script.js           # GA4 + події
├── assets/
│   ├── og-image.png    # 1200x630px для шерінгу
│   ├── favicon.ico
│   └── demo/           # Скріни для демо-блоку
└── README.md
```

---

# ЧАСТИНА 1: ЛЕНДІНГ

## Структура сторінки (5 блоків)

```
┌─────────────────────────────────────────┐
│            HEADER (sticky)              │
│  Logo          [Запустити бота]         │
├─────────────────────────────────────────┤
│                                         │
│              🎬 HERO                    │
│                                         │
│  Не знаєш, що подивитись?               │
│  Бот підбере фільм за 30 секунд         │
│                                         │
│     [🎬 Підібрати фільм зараз]          │
│                                         │
├─────────────────────────────────────────┤
│                                         │
│          ЯК ЦЕ ПРАЦЮЄ                   │
│                                         │
│   📱          💬          🎬            │
│ Відкриваєш   Пишеш      Дивишся         │
│   бота       настрій    фільм           │
│                                         │
├─────────────────────────────────────────┤
│                                         │
│         ПРИКЛАДИ РЕКОМЕНДАЦІЙ           │
│                                         │
│  ┌─────┐  ┌─────┐  ┌─────┐              │
│  │Demo1│  │Demo2│  │Demo3│              │
│  └─────┘  └─────┘  └─────┘              │
│                                         │
├─────────────────────────────────────────┤
│                                         │
│              FAQ                        │
│                                         │
│  ▸ Це безкоштовно?                      │
│  ▸ Потрібна реєстрація?                 │
│  ▸ Звідки бот знає, що мені сподобається│
│                                         │
├─────────────────────────────────────────┤
│                                         │
│          ФІНАЛЬНИЙ CTA                  │
│                                         │
│  Готовий дізнатись, що дивитись?        │
│                                         │
│     [🎬 Запустити бота в Telegram]      │
│            [Канал з підбірками]         │
│                                         │
└─────────────────────────────────────────┘
```

---

## Контент для блоків

### БЛОК 1: Hero

**Заголовок (вибрати один):**
```
Варіант A: "Не знаєш, що подивитись?"
Варіант B: "Фільм на вечір — без години гортання"
Варіант C: "30 секунд — і дивишся ідеальний фільм"
```

**Підзаголовок:**
```
Telegram-бот, який підбирає фільми за настроєм, жанром або просто каже "дивись це — не пошкодуєш"
```

**CTA-кнопка:**
```
Текст: "Підібрати фільм зараз"
Посилання: https://t.me/YOUR_BOT?start=hero
```

**Під кнопкою (знімає тривогу):**
```
Безкоштовно · Без реєстрації · Відкриється Telegram
```

---

### БЛОК 2: Як це працює

**Заголовок:** "Як це працює"

**3 кроки:**

| Крок | Іконка | Заголовок | Підпис |
|------|--------|-----------|--------|
| 1 | 📱 | Відкриваєш бота | Один клік — і ти в Telegram |
| 2 | 💬 | Пишеш, що хочеш | "Щось легке" або "трилер з поворотом" |
| 3 | 🎬 | Отримуєш фільм | З рейтингом, описом і де дивитись |

---

### БЛОК 3: Приклади рекомендацій

**Заголовок:** "Подивись, як це виглядає"

**Картка 1:**
```
💬 Запит: "Хочу посміятись після важкого дня"

🎬 Рекомендація:
   Круелла (2021)
   ⭐ 7.4 · Комедія, драма · 134 хв
   
   "Стильний, дотепний, з Еммою Стоун.
   Ідеально щоб перезавантажитись."
```

**Картка 2:**
```
💬 Запит: "Трилер з несподіваним фіналом"

🎬 Рекомендація:
   Гра (1997)
   ⭐ 7.7 · Трилер, детектив · 129 хв
   
   "Фінчер у найкращій формі.
   Кінцівка — ого."
```

**Картка 3:**
```
💬 Запит: "На вечір удвох, щось атмосферне"

🎬 Рекомендація:
   Одного разу в Голлівуді (2019)
   ⭐ 7.6 · Драма, комедія · 161 хв
   
   "Тарантіно, але м'який.
   Красиво, стильно, затишно."
```

---

### БЛОК 4: FAQ

**Заголовок:** "Часті питання"

**Питання та відповіді (акордеон):**

```
▸ Це безкоштовно?
  Так, повністю. Без підписок, без прихованих платежів.

▸ Потрібна реєстрація?
  Ні. Просто відкриваєш бота в Telegram і пишеш.

▸ Звідки бот знає, що мені сподобається?
  Аналізує твій запит + база з 10 000+ фільмів з рейтингами та відгуками.
```

---

### БЛОК 5: Фінальний CTA

**Заголовок:** "Готовий дізнатись, що дивитись сьогодні?"

**Текст:**
```
Натисни кнопку — через хвилину матимеш ідеальний фільм на вечір.
```

**Кнопки:**
```
Головна: "Запустити бота в Telegram"
         https://t.me/YOUR_BOT?start=footer

Друга:   "Підписатись на канал"
         https://t.me/YOUR_CHANNEL
```

---

# ЧАСТИНА 2: ТЕХНІЧНА КОНФІГУРАЦІЯ

## Meta-теги

```html
<!-- Основні -->
<title>Бот для підбору фільмів у Telegram — знайди що подивитись за 30 секунд</title>
<meta name="description" content="Не знаєш, що подивитись? Telegram-бот підбере ідеальний фільм за настроєм, жанром або часом. Безкоштовно, без реєстрації.">
<meta name="viewport" content="width=device-width, initial-scale=1">

<!-- Open Graph (для шерінгу) -->
<meta property="og:title" content="Бот підбере фільм на вечір за 30 секунд">
<meta property="og:description" content="Telegram-бот, який знає, що тобі сподобається. Безкоштовно.">
<meta property="og:image" content="https://YOUR_DOMAIN/assets/og-image.png">
<meta property="og:url" content="https://YOUR_DOMAIN">
<meta property="og:type" content="website">

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Бот підбере фільм на вечір за 30 секунд">
<meta name="twitter:description" content="Telegram-бот, який знає, що тобі сподобається">
<meta name="twitter:image" content="https://YOUR_DOMAIN/assets/og-image.png">
```

---

## Google Analytics 4

**Крок 1: Підключення (в `<head>`):**
```html
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

**Крок 2: Події для відстеження:**
```javascript
// Клік на CTA (додати на кожну кнопку)
function trackCTA(location) {
  gtag('event', 'cta_click', {
    'event_category': 'engagement',
    'event_label': location // 'hero', 'footer', 'header'
  });
}

// Скрол до секції
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      gtag('event', 'section_view', {
        'event_label': entry.target.id
      });
    }
  });
}, { threshold: 0.5 });

document.querySelectorAll('section').forEach(section => {
  observer.observe(section);
});
```

**Крок 3: UTM-мітки на кнопках:**
```
Hero CTA:     https://t.me/BOT?start=utm_hero
Footer CTA:   https://t.me/BOT?start=utm_footer
Header CTA:   https://t.me/BOT?start=utm_header
Channel:      https://t.me/CHANNEL?start=utm_landing
```

---

## Стилі (ключові моменти)

```css
/* Mobile-first */
* { box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  line-height: 1.6;
  color: #1a1a1a;
}

/* CTA-кнопка */
.cta-primary {
  background: #0088cc; /* Telegram blue */
  color: white;
  padding: 16px 32px;
  border-radius: 12px;
  font-size: 18px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.cta-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 136, 204, 0.4);
}

/* Адаптивність */
@media (max-width: 768px) {
  .hero h1 { font-size: 28px; }
  .steps { flex-direction: column; }
  .demo-cards { flex-direction: column; }
}
```

---

# ЧАСТИНА 3: ОНБОРДИНГ БОТА

## Флоу першого контакту

```
КОРИСТУВАЧ: /start

БОТ:
┌─────────────────────────────────────────┐
│  👋 Привіт! Я підберу фільм             │
│  за 30 секунд.                          │
│                                         │
│  Що хочеш сьогодні?                     │
│                                         │
│  [😂 Посміятись]  [😰 Потрилерити]      │
│  [🥰 Романтику]   [🎲 Здивуй мене]      │
└─────────────────────────────────────────┘

КОРИСТУВАЧ: [клік на будь-яку кнопку]

БОТ:
┌─────────────────────────────────────────┐
│  🎬 Круелла (2021)                      │
│  ⭐ 7.4/10 · Комедія, драма · 134 хв    │
│                                         │
│  Історія про те, як зʼявилась одна з    │
│  найвідоміших лиходійок Disney.         │
│  Стильно, дотепно, з Еммою Стоун.       │
│                                         │
│  📺 Де дивитись: Netflix, Apple TV      │
│                                         │
│  [👍 Подобається] [👎 Інший варіант]    │
└─────────────────────────────────────────┘

БОТ (після реакції):
┌─────────────────────────────────────────┐
│  💡 До речі, у каналі — щоденні         │
│  підбірки фільмів і опитування.         │
│                                         │
│  👉 @YOUR_CHANNEL                       │
│                                         │
│  Або напиши мені будь-коли —            │
│  підберу ще!                            │
└─────────────────────────────────────────┘
```

---

## Ключові принципи онбордингу

| Принцип | Реалізація |
|---------|------------|
| Миттєвий результат | Перша рекомендація за 1 клік |
| Кнопки замість тексту | Не треба думати що писати |
| Конкретика | Назва + рейтинг + де дивитись |
| Один CTA за раз | Спочатку фільм, потім канал |
| Без нав'язливості | Канал пропонуємо 1 раз |

---

# ЧАСТИНА 4: МЕТРИКИ

## Що відстежувати

| Метрика | Як рахувати | Норма | Проблема |
|---------|-------------|-------|----------|
| **Конверсія лендінг → клік** | Кліки CTA / Відвідувачі | 8-15% | < 5% |
| **Конверсія клік → /start** | Старти / Кліки | 60-80% | < 50% |
| **Перша рекомендація** | Видані рекомендації / Старти | 80-90% | < 70% |

## Де дивитись

- **Лендінг:** Google Analytics 4 → Events
- **Бот:** Telegram Bot API → вбудована статистика або свій лог

---

# ЧАСТИНА 5: ПІСЛЯ ЗАПУСКУ (v2)

## Додати коли буде 500+ користувачів

| Фіча | Коли | Навіщо |
|------|------|--------|
| Соціальний доказ | 500+ юзерів | Реальні цифри переконують |
| Відгуки | 10+ фідбеків | Справжні слова краще вигаданих |
| Блог (1 стаття) | 1000+ юзерів | SEO починає працювати |
| A/B тест заголовків | 2000+ відвідувачів | Потрібен трафік для статистики |
| Ретеншен-пуші | 500+ юзерів | Є кого повертати |

---

# ЧЕК-ЛИСТ ЗАПУСКУ

## До запуску

- [ ] Лендінг зверстано (5 блоків)
- [ ] Мобільна версія працює
- [ ] CTA-кнопки ведуть на бота з UTM
- [ ] Meta-теги заповнені
- [ ] OG-картинка готова (1200x630)
- [ ] GA4 підключено
- [ ] Події відстежуються (клік, скрол)
- [ ] Онбординг бота працює
- [ ] Перша рекомендація видається за 1 клік

## Запуск (день 1)

- [ ] Пост у своєму Telegram-каналі
- [ ] Посилання 5-10 друзям для тесту
- [ ] Перевірити що все працює на телефоні

## Тиждень 1

- [ ] Зібрати перший фідбек
- [ ] Подивитись метрики в GA4
- [ ] Пофіксити очевидні проблеми

---

# ЧАСТИНА 6: ГЕНІАЛЬНІ ФІЧІ

## 6.1 Міні-демо прямо на сайті

**Концепція:** Користувач пробує бота БЕЗ переходу в Telegram

```
┌─────────────────────────────────────────┐
│                                         │
│  Не знаєш, що подивитись?               │
│  Спробуй прямо зараз 👇                 │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ Який настрій сьогодні?          │    │
│  │                                 │    │
│  │ [😂 Посміятись] [😰 Трилер]     │    │
│  │ [🥰 Романтика]  [🎲 Здивуй]     │    │
│  └─────────────────────────────────┘    │
│                                         │
│         ↓ після кліку ↓                 │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ 🎬 Круелла (2021)               │    │
│  │ ⭐ 7.4 · Комедія · 134 хв       │    │
│  │ "Стильно, дотепно, з Еммою"     │    │
│  │                                 │    │
│  │ [🎬 Ще 10 комедій в Telegram →] │    │
│  └─────────────────────────────────┘    │
│                                         │
└─────────────────────────────────────────┘
```

**Реалізація:**

```javascript
// Захардкоджена база фільмів (10-15 на категорію)
const movies = {
  comedy: [
    {
      title: "Круелла",
      year: 2021,
      rating: 7.4,
      genre: "Комедія, драма",
      duration: "134 хв",
      description: "Стильно, дотепно, з Еммою Стоун",
      poster: "/assets/posters/cruella.jpg"
    },
    // ... ще 10-15 комедій
  ],
  thriller: [/* ... */],
  romance: [/* ... */],
  random: [/* ... */]
};

// Показати рандомний фільм з категорії
function showMovie(category) {
  const list = movies[category];
  const movie = list[Math.floor(Math.random() * list.length)];
  
  // Анімація появи картки
  renderMovieCard(movie);
  
  // Персоналізувати CTA
  updateCTA(category);
  
  // Трекінг
  gtag('event', 'demo_interaction', { category });
}

// Персоналізований CTA після вибору
function updateCTA(category) {
  const ctaTexts = {
    comedy: "Ще 10 комедій в Telegram →",
    thriller: "Більше трилерів — в боті →",
    romance: "Романтика на вечір — в боті →",
    random: "Ще більше сюрпризів →"
  };
  document.querySelector('.cta-text').textContent = ctaTexts[category];
}
```

---

## 6.2 Лайв-стрічка рекомендацій

**Концепція:** Фейковий "реальний час" — соціальний доказ без реальних даних

```
┌─────────────────────────────────────────┐
│  🔴 Зараз підбирають:                   │
│                                         │
│  Марія з Києва отримала "Інтерстеллар"  │
│  ← змінюється кожні 4-6 сек             │
│                                         │
│  📊 Сьогодні підібрано: 1,247 фільмів   │
└─────────────────────────────────────────┘
```

**Реалізація:**

```javascript
const names = ["Марія", "Андрій", "Оля", "Денис", "Катя", "Максим", "Юля", "Олег"];
const cities = ["Києва", "Львова", "Одеси", "Харкова", "Дніпра"];
const actions = [
  { verb: "отримала", film: "Інтерстеллар" },
  { verb: "шукає", film: "щось як Шерлок" },
  { verb: "дивиться", film: "Паразити" },
  { verb: "отримав", film: "Дюна" },
  { verb: "обрала", film: "Круелла" },
  // ... ще 20-30 варіантів
];

function updateLiveFeed() {
  const name = names[Math.floor(Math.random() * names.length)];
  const city = cities[Math.floor(Math.random() * cities.length)];
  const action = actions[Math.floor(Math.random() * actions.length)];
  
  const text = `${name} з ${city} ${action.verb} "${action.film}"`;
  
  // Анімація fade
  const feed = document.querySelector('.live-feed');
  feed.style.opacity = 0;
  setTimeout(() => {
    feed.textContent = text;
    feed.style.opacity = 1;
  }, 300);
}

// Оновлювати кожні 4-6 секунд (рандомно для реалістичності)
function scheduleFeedUpdate() {
  const delay = 4000 + Math.random() * 2000;
  setTimeout(() => {
    updateLiveFeed();
    scheduleFeedUpdate();
  }, delay);
}

// Лічильник "підібрано сьогодні"
function updateCounter() {
  const base = 800 + Math.floor(Math.random() * 500);
  const counter = document.querySelector('.counter');
  counter.textContent = base.toLocaleString('uk-UA');
  
  // Іноді збільшувати на 1
  setInterval(() => {
    if (Math.random() > 0.7) {
      const current = parseInt(counter.textContent.replace(/\s/g, ''));
      counter.textContent = (current + 1).toLocaleString('uk-UA');
    }
  }, 10000);
}
```

---

## 6.3 Автоматичний контекст (час доби)

**Концепція:** Сайт адаптується до часу

```javascript
function getTimeContext() {
  const hour = new Date().getHours();
  const day = new Date().getDay();
  const isWeekend = day === 0 || day === 6;
  
  if (isWeekend) {
    return {
      greeting: "Вихідний. Час для марафону 🍿",
      theme: "relaxed",
      suggestions: ["Серіал", "Довгий фільм", "Трилогія"]
    };
  }
  
  if (hour >= 6 && hour < 12) {
    return {
      greeting: "Доброго ранку! Плануєш вечір?",
      theme: "light",
      suggestions: ["Комедія", "Легкий", "Короткий"]
    };
  }
  
  if (hour >= 12 && hour < 18) {
    return {
      greeting: "Не знаєш, що подивитись ввечері?",
      theme: "light",
      suggestions: ["Драма", "Трилер", "Документалка"]
    };
  }
  
  if (hour >= 18 && hour < 23) {
    return {
      greeting: "Вечір. Час для фільму.",
      theme: "dark",
      suggestions: ["Що завгодно", "Розслабитись", "Щось нове"]
    };
  }
  
  // Ніч
  return {
    greeting: "Не спиться? Є що подивитись.",
    theme: "dark",
    suggestions: ["Короткий", "Легкий", "Заспокійливий"]
  };
}

// Застосувати тему
function applyContext() {
  const ctx = getTimeContext();
  document.querySelector('.hero-title').textContent = ctx.greeting;
  document.body.setAttribute('data-theme', ctx.theme);
}
```

**CSS для темної теми:**

```css
[data-theme="dark"] {
  --bg-color: #1a1a2e;
  --text-color: #eaeaea;
  --card-bg: #16213e;
  --accent: #0f94d2;
}

[data-theme="light"] {
  --bg-color: #ffffff;
  --text-color: #1a1a1a;
  --card-bg: #f5f5f5;
  --accent: #0088cc;
}

body {
  background: var(--bg-color);
  color: var(--text-color);
  transition: background 0.3s, color 0.3s;
}
```

---

## 6.4 "Зберегти на потім" (localStorage)

**Концепція:** Людина зберігає фільми → мотивація перейти в Telegram

```
┌─────────────────────────────────────────┐
│  🎬 Круелла (2021)                      │
│  ⭐ 7.4 · Комедія                       │
│                                         │
│  [💾 Зберегти] [🔄 Інший]               │
└─────────────────────────────────────────┘

        ↓ після кількох збережень ↓

┌─────────────────────────────────────────┐
│  💾 Збережено: 3 фільми                 │
│                                         │
│  • Круелла (2021)                       │
│  • Гра (1997)                           │
│  • Дюна (2021)                          │
│                                         │
│  [📲 Отримати список в Telegram]        │
└─────────────────────────────────────────┘
```

**Реалізація:**

```javascript
// Зберегти фільм
function saveMovie(movie) {
  const saved = JSON.parse(localStorage.getItem('savedMovies') || '[]');
  
  // Перевірити чи вже є
  if (!saved.find(m => m.title === movie.title)) {
    saved.push(movie);
    localStorage.setItem('savedMovies', JSON.stringify(saved));
    updateSavedUI();
    
    gtag('event', 'movie_saved', { title: movie.title });
  }
}

// Оновити UI збережених
function updateSavedUI() {
  const saved = JSON.parse(localStorage.getItem('savedMovies') || '[]');
  const container = document.querySelector('.saved-movies');
  
  if (saved.length === 0) {
    container.style.display = 'none';
    return;
  }
  
  container.style.display = 'block';
  container.querySelector('.count').textContent = saved.length;
  
  const list = container.querySelector('.list');
  list.innerHTML = saved.map(m => `<li>${m.title} (${m.year})</li>`).join('');
  
  // Якщо 3+ фільми — показати CTA
  if (saved.length >= 3) {
    container.querySelector('.telegram-cta').style.display = 'block';
  }
}

// Передати список в Telegram через deep link
function sendToTelegram() {
  const saved = JSON.parse(localStorage.getItem('savedMovies') || '[]');
  const titles = saved.map(m => m.title).join(',');
  const encoded = encodeURIComponent(titles);
  
  window.location.href = `https://t.me/YOUR_BOT?start=saved_${encoded}`;
}
```

---

## 6.5 Фінальна структура Hero

```html
<section class="hero" id="hero">
  <!-- Контекстний заголовок -->
  <h1 class="hero-title">Вечір. Час для фільму.</h1>
  
  <!-- Інтерактивне демо -->
  <div class="demo-widget">
    <p class="demo-prompt">Що хочеш сьогодні?</p>
    
    <div class="mood-buttons">
      <button onclick="showMovie('comedy')">😂 Посміятись</button>
      <button onclick="showMovie('thriller')">😰 Трилер</button>
      <button onclick="showMovie('romance')">🥰 Романтика</button>
      <button onclick="showMovie('random')">🎲 Здивуй</button>
    </div>
    
    <!-- Результат (прихований до кліку) -->
    <div class="movie-result" style="display: none;">
      <div class="movie-card">
        <img class="poster" src="" alt="">
        <div class="info">
          <h3 class="title"></h3>
          <p class="meta"></p>
          <p class="description"></p>
        </div>
        <div class="actions">
          <button class="save-btn" onclick="saveMovie(currentMovie)">💾 Зберегти</button>
          <button class="another-btn" onclick="showAnother()">🔄 Інший</button>
        </div>
      </div>
      
      <a class="cta-telegram" href="#">
        <span class="cta-text">Ще 10 комедій в Telegram →</span>
      </a>
    </div>
  </div>
  
  <!-- Лайв-стрічка -->
  <div class="live-feed-container">
    <span class="live-dot">🔴</span>
    <span class="live-feed">Марія з Києва отримала "Інтерстеллар"</span>
  </div>
  
  <!-- Збережені фільми -->
  <div class="saved-movies" style="display: none;">
    <p>💾 Збережено: <span class="count">0</span> фільмів</p>
    <ul class="list"></ul>
    <a class="telegram-cta" href="#" onclick="sendToTelegram()" style="display: none;">
      📲 Отримати список в Telegram
    </a>
  </div>
  
  <!-- Лічильник -->
  <p class="counter-text">📊 Сьогодні підібрано: <span class="counter">1,247</span> фільмів</p>
</section>
```

---

# ШВИДКИЙ СТАРТ ДЛЯ CLAUDE CODE

## Команда 1: Базова структура
```
Створи проєкт лендінга для Telegram-бота підбору фільмів:
- index.html з секціями: Hero, Як працює, FAQ, Фінальний CTA
- styles.css (mobile-first, підтримка світлої/темної теми через CSS variables)
- script.js (базова логіка)
- Контент українською з документа
```

## Команда 2: Інтерактивне демо
```
Додай в Hero інтерактивний віджет:
- 4 кнопки настрою (Комедія, Трилер, Романтика, Рандом)
- Захардкоджена база 15 фільмів на категорію (title, year, rating, genre, duration, description)
- По кліку показує рандомний фільм з анімацією
- Персоналізований CTA після вибору ("Ще 10 комедій в Telegram")
- Кнопка "Інший" для повторного вибору
```

## Команда 3: Соціальний доказ
```
Додай:
- Лайв-стрічку: фейкові повідомлення "Марія з Києва отримала Інтерстеллар"
- Масиви імен (10), міст (5), фільмів (30)
- Оновлення кожні 4-6 сек з fade-анімацією
- Лічильник "Сьогодні підібрано: X фільмів" (стартує з 800-1200, іноді +1)
```

## Команда 4: Контекст часу
```
Додай автоматичну адаптацію під час доби:
- getTimeContext() — визначає період (ранок/день/вечір/ніч/вихідні)
- Змінює заголовок Hero під контекст
- Перемикає світлу/темну тему
- CSS variables для обох тем
```

## Команда 5: Збереження фільмів
```
Додай функцію "Зберегти на потім":
- localStorage для збережених фільмів
- Кнопка "Зберегти" на картці фільму
- Блок "Збережено: X фільмів" зі списком
- Після 3+ фільмів — CTA "Отримати список в Telegram"
- Deep link з закодованими назвами фільмів
```

## Команда 6: Аналітика та фінал
```
Додай:
- GA4 з подіями: demo_interaction, movie_saved, cta_click, section_view
- UTM-мітки на всі Telegram-посилання
- Meta-теги (title, description, OG, Twitter)
- Фінальна оптимізація мобільної версії
```

---

# ЗАМІНИ ПЕРЕД ЗАПУСКОМ

```
YOUR_BOT      → @назва_твого_бота
YOUR_CHANNEL  → @назва_твого_каналу
YOUR_DOMAIN   → твійдомен.com
G-XXXXXXXXXX  → твій GA4 ID
```

---

*Готово до імплементації. Почни з Команди 1 в Claude Code.*
