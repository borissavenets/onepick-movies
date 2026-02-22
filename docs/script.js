// OnePick Movies landing - scripts

// --- Theme toggle ---
(function () {
  var toggle = document.getElementById('themeToggle');
  var html = document.documentElement;
  var stored = localStorage.getItem('theme');

  if (stored) {
    html.setAttribute('data-theme', stored);
  }

  toggle.addEventListener('click', function () {
    var next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
  });
})();

// --- Fade-in on scroll ---
(function () {
  var items = document.querySelectorAll('.fade-in');

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });

  items.forEach(function (el) { observer.observe(el); });
})();

// --- Time context ---
(function () {
  var h = new Date().getHours();
  var day = new Date().getDay();
  var isWeekend = day === 0 || day === 6;
  var title = document.querySelector('.hero__title');

  if (isWeekend) {
    title.textContent = 'Вихідний. Час для кіно';
  } else if (h >= 6 && h < 12) {
    title.textContent = 'Плануєш вечір? Підберемо фільм';
  } else if (h >= 12 && h < 18) {
    title.textContent = 'Не знаєш, що подивитись ввечері?';
  } else if (h >= 18 && h < 23) {
    title.textContent = 'Вечір. Час для фільму';
  } else {
    title.textContent = 'Не спиться? Є що подивитись';
  }
})();

// --- Live feed ---
(function () {
  var names = [
    'Марія', 'Андрій', 'Оля', 'Денис', 'Катя',
    'Максим', 'Юля', 'Олег', 'Даша', 'Артем'
  ];
  var cities = ['Києва', 'Львова', 'Одеси', 'Харкова', 'Дніпра'];
  var films = [
    'Interstellar', 'Паразити', 'La La Land', 'Дюна', 'Whiplash',
    'Gone Girl', 'Амелі', 'Se7en', 'Jojo Rabbit', 'Knives Out',
    'About Time', 'Sicario', 'The Truman Show', 'Shutter Island',
    'Superbad', 'The Grand Budapest Hotel', 'The Intern'
  ];
  var verbs = ['отримав', 'отримала'];

  var feed = document.getElementById('liveFeed');
  var counter = document.getElementById('liveCounter');

  var count = 800 + Math.floor(Math.random() * 500);
  counter.textContent = count.toLocaleString('uk-UA');

  function pick(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function update() {
    var name = pick(names);
    var isFemale = name.slice(-1) === 'а' || name.slice(-1) === 'я';
    var verb = isFemale ? 'отримала' : 'отримав';
    var text = name + ' з ' + pick(cities) + ' ' + verb + ' "' + pick(films) + '"';

    feed.style.opacity = '0';
    setTimeout(function () {
      feed.textContent = text;
      feed.style.opacity = '1';
    }, 300);
  }

  function schedule() {
    var delay = 4000 + Math.random() * 3000;
    setTimeout(function () {
      update();
      schedule();
    }, delay);
  }

  update();
  schedule();

  setInterval(function () {
    if (Math.random() > 0.6) {
      count++;
      counter.textContent = count.toLocaleString('uk-UA');
    }
  }, 8000);
})();

// --- Interactive demo ---
(function () {
  var IMG = 'https://image.tmdb.org/t/p/w300';

  var movies = {
    comedy: [
      { title: 'The Grand Budapest Hotel', year: 2014, genre: 'Комедія', rating: 8.1, poster: '/eWdyYQreja6JGCzqHWXpWHDrrPo.jpg', desc: 'Візуально розкішний фільм з гумором Веса Андерсона. Ідеально для легкого вечора.' },
      { title: 'Knives Out', year: 2019, genre: 'Комедія, детектив', rating: 7.9, poster: '/pThyQovXQrw2m0s9x82twj48Jq4.jpg', desc: 'Сучасний детектив з блискучим кастом. Жодного нудного моменту.' },
      { title: 'Superbad', year: 2007, genre: 'Комедія', rating: 7.6, poster: '/ek8e8txUyUwd2BNqj6lFEerJfbq.jpg', desc: 'Класика підліткової комедії. Смішно, трохи безглуздо, але щиро.' },
      { title: 'The Intern', year: 2015, genre: 'Комедія, драма', rating: 7.1, poster: '/bTQ46fupPbjBfFBHuzfD3hxxL0Q.jpg', desc: 'Де Ніро й Етевей у затишній історії про дружбу між поколіннями.' },
      { title: 'Jojo Rabbit', year: 2019, genre: 'Комедія, драма', rating: 7.9, poster: '/7GsM4mtM0worCtIVeiQt28HieeN.jpg', desc: 'Смішно і зворушливо. Тайка Вайтіті знову вражає.' }
    ],
    thriller: [
      { title: 'Sicario', year: 2015, genre: 'Трилер', rating: 7.6, poster: '/lz8vNyXeidqqOdJW9ZjnDAMb5Vr.jpg', desc: 'Напружений трилер про картелі на кордоні. Тримає до останньої хвилини.' },
      { title: 'Gone Girl', year: 2014, genre: 'Трилер, драма', rating: 8.1, poster: '/ts996lKsxvjkO2yiYG0ht4qAicO.jpg', desc: 'Ідеальне подружжя? Ні. Ідеальний трилер? Так.' },
      { title: 'Паразити', year: 2019, genre: 'Трилер, драма', rating: 8.5, poster: '/7IiTTgloJzvGI1TAYymCfbfl3vT.jpg', desc: 'Оскар за найкращий фільм. Жанр неможливо визначити заздалегідь.' },
      { title: 'Shutter Island', year: 2010, genre: 'Трилер', rating: 8.2, poster: '/nrmXQ0zcZUL8jFLrakWc90IR8z9.jpg', desc: 'ДіКапріо на острові-психлікарні. Скорсезе крутить мозок.' },
      { title: 'Se7en', year: 1995, genre: 'Трилер, детектив', rating: 8.6, poster: '/191nKfP0ehp3uIvWqgPbFmI4lv9.jpg', desc: 'Фінчер у найкращій формі. Кінцівка - ого.' }
    ],
    romance: [
      { title: 'The Secret Life of Walter Mitty', year: 2013, genre: 'Пригоди, драма', rating: 7.3, poster: '/tY6ypjKOOtujhxiSwTmvA4OZ5IE.jpg', desc: 'Подорож з дивана на край світу. Атмосферно й надихаюче.' },
      { title: 'About Time', year: 2013, genre: 'Романтика, драма', rating: 7.8, poster: '/ls6zswrOZVhCXQBh96DlbnLBajM.jpg', desc: 'Подорожі в часі заради кохання. Один з найзворушливіших фільмів.' },
      { title: 'La La Land', year: 2016, genre: 'Романтика, мюзикл', rating: 8.0, poster: '/uDO8zWDhfWwoFdKS4fzkUJt0Rf0.jpg', desc: 'Музика, Лос-Анджелес, кохання. Красиво до болю.' },
      { title: 'Амелі', year: 2001, genre: 'Романтика, комедія', rating: 8.3, poster: '/nSxDa3M9aMvGVLoItzWTepQ5h5d.jpg', desc: 'Паризька казка про дівчину, яка робить світ кращим.' },
      { title: 'Eternal Sunshine of the Spotless Mind', year: 2004, genre: 'Романтика, фантастика', rating: 8.3, poster: '/5MwkWH9tYHv3mV9OdYTMR5qreIz.jpg', desc: 'Що якщо стерти пам\'ять про кохання? Глибоко і незвичайно.' }
    ],
    random: [
      { title: 'Interstellar', year: 2014, genre: 'Фантастика, драма', rating: 8.7, poster: '/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg', desc: 'Нолан про космос, час і батьківську любов. Епічно.' },
      { title: 'Whiplash', year: 2014, genre: 'Драма, музичний', rating: 8.5, poster: '/7fn624j5lj3xTme2SgiLCeuedmO.jpg', desc: '106 хвилин чистої напруги про ціну досконалості.' },
      { title: 'Everything Everywhere All at Once', year: 2022, genre: 'Фантастика, комедія', rating: 7.8, poster: '/u68AjlvlutfEIcpmbYpKcdi09ut.jpg', desc: 'Мультивсесвіт, але з серцем. Смієшся й плачеш одночасно.' },
      { title: 'The Truman Show', year: 1998, genre: 'Драма, фантастика', rating: 8.2, poster: '/vuza0WqY239yBXOadKlGwJsZJFE.jpg', desc: 'Що якщо твоє життя - телешоу? Керрі у найкращій ролі.' },
      { title: 'Дюна', year: 2021, genre: 'Фантастика', rating: 8.0, poster: '/d5NXSklXo0qyIYkgV94XAgMIckC.jpg', desc: 'Візуальна поезія. Вільньов не розчаровує.' }
    ]
  };

  var ctaTexts = {
    comedy: 'Ще більше комедій в боті',
    thriller: 'Більше трилерів - в боті',
    romance: 'Романтика на вечір - в боті',
    random: 'Ще більше сюрпризів в боті'
  };

  var buttons = document.querySelectorAll('.demo__btn');
  var result = document.getElementById('demoResult');
  var currentMood = null;
  var lastIndex = {};

  function pickRandom(mood) {
    var list = movies[mood];
    var idx;
    do {
      idx = Math.floor(Math.random() * list.length);
    } while (idx === lastIndex[mood] && list.length > 1);
    lastIndex[mood] = idx;
    return list[idx];
  }

  function showMovie(mood) {
    currentMood = mood;
    var m = pickRandom(mood);

    buttons.forEach(function (b) {
      b.classList.toggle('active', b.getAttribute('data-mood') === mood);
    });

    result.innerHTML =
      '<div class="demo__card">' +
        '<div class="demo__card-top">' +
          '<img class="demo__poster" src="' + IMG + m.poster + '" alt="' + m.title + '" loading="lazy">' +
          '<div class="demo__card-info">' +
            '<div class="demo__card-title">' + m.title + '</div>' +
            '<div class="demo__card-meta">' + m.genre + ' / ' + m.year + ' / ' + m.rating + '</div>' +
          '</div>' +
        '</div>' +
        '<p class="demo__card-text">' + m.desc + '</p>' +
        '<div class="demo__actions">' +
          '<a href="https://t.me/onepick_movies_bot?start=ref_site_demo" class="btn" target="_blank" rel="noopener">' +
            ctaTexts[mood] +
          '</a>' +
          '<button class="btn btn--outline" id="demoAnother">Інший</button>' +
        '</div>' +
      '</div>';

    document.getElementById('demoAnother').addEventListener('click', function () {
      showMovie(currentMood);
    });
  }

  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      showMovie(this.getAttribute('data-mood'));
    });
  });
})();

// --- GA4 analytics ---
(function () {
  // guard: skip if gtag not loaded
  function ga(event, params) {
    if (typeof gtag === 'function') gtag('event', event, params);
  }

  // CTA clicks
  document.querySelectorAll('a[href*="t.me/"]').forEach(function (link) {
    link.addEventListener('click', function () {
      var url = this.href;
      var label = 'unknown';
      if (url.indexOf('ref_site_header') !== -1) label = 'header';
      else if (url.indexOf('ref_site_hero') !== -1) label = 'hero';
      else if (url.indexOf('ref_site_demo') !== -1) label = 'demo';
      else if (url.indexOf('ref_site_footer') !== -1) label = 'footer';
      else if (url.indexOf('OnePickMovies') !== -1) label = 'channel';
      ga('cta_click', { event_label: label });
    });
  });

  // Demo interactions
  document.querySelectorAll('.demo__btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      ga('demo_interaction', { mood: this.getAttribute('data-mood') });
    });
  });

  // Section views
  var sections = document.querySelectorAll('section[id]');
  var viewObserver = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        ga('section_view', { event_label: entry.target.id });
        viewObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.3 });

  sections.forEach(function (s) { viewObserver.observe(s); });
})();
