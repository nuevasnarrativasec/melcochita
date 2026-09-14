/* ============================================================
   ¡ESCUCHA BIEN! — Carrusel horizontal de álbumes de Melcochita
   - Arrastre con cursor (desktop) + swipe nativo (móvil)
   - Flechas amarillas de navegación (anterior / siguiente)
   - Botón play reproduce el embed de Spotify
   - Solo un álbum suena a la vez (sin reproducción solapada)
   ============================================================ */
(function () {
  'use strict';

  /* ---------- 1. DATA ----------
     Edita este arreglo para agregar/editar álbumes.
     - cover: ruta de la portada (en ./img/) -> también se usa como
       etiqueta del vinilo.
     - spotify: URI del álbum -> 'spotify:album:XXXXXXXX'
       (copia el ID desde la URL del álbum en Spotify)
     NOTA: los IDs de Spotify son álbumes REALES de Melcochita que
     sirven de demo para que la reproducción funcione ya mismo.
     Reemplázalos por el que corresponde a cada portada. */
  const ALBUMES = [
    {
      cover: './img/portada-disco-1.png',
      titulo: '“Karamanduka y Melcochita with Mag Peruvian All Stars” (1969)',
      descripcion: 'Uno de los registros que muestran la faceta salsera de Melcochita junto a Karamanduka y músicos peruanos. Resume una etapa en la que consolidaba su voz y oficio como sonero.',
      spotify: 'spotify:album:1ywBoxqGjaqWWQVaHD1LbY'
    },
    {
      cover: './img/portada-disco-1.png',
      titulo: '“Acabo con Lima, huyo pa’ New York” (1969)',
      descripcion: 'Grabado junto a Karamanduka para Fania Records, este LP conecta directamente a Melcochita con la industria salsera internacional y con una etapa clave de su carrera fuera del Perú.',
      spotify: 'spotify:album:1ywBoxqGjaqWWQVaHD1LbY'
    },
    {
      cover: './img/portada-disco-2.png',
      titulo: '“Picardías de Melcochita” (1976)',
      descripcion: 'Un título ligado a la personalidad irreverente y popular que acompañó siempre a Melcochita. El disco forma parte de una discografía que combina sabor, humor y tradición salsera.',
      spotify: 'spotify:album:4fbLCjbjWTZLa0NFtaGUK9'
    },
    {
      cover: './img/portada-disco-3.png',
      titulo: '“A comer lechón” (1986)',
      descripcion: 'Otro de los títulos registrados en su discografía. Refleja el tono festivo asociado a Melcochita y su vínculo con una salsa pensada para el baile, la calle y la celebración popular.',
      spotify: 'spotify:album:6FCwtnOjb6AcK6M08VvuEb'
    },
    {
      cover: './img/portada-disco-4.png',
      titulo: '“La estrella del son” (1989)',
      descripcion: 'Grabado junto a Johnny Pacheco, es uno de los trabajos que mejor conecta a Melcochita con las grandes figuras de la salsa internacional y confirma su reconocimiento como sonero.',
      spotify: 'spotify:album:2ztdZWGohlS94pQAv8wGZh'
    },
    {
      cover: './img/portada-disco-5.png',
      titulo: '“Con sabor a pueblo” (1986)',
      descripcion: 'Un disco cuyo título resume una de las marcas de su carrera musical: una salsa cercana, popular y conectada con la calle, el humor y las experiencias cotidianas de su público.',
      spotify: 'spotify:album:1A71noWxYqcFnSMbLMDCid'
    },
    {
      cover: './img/portada-disco-6.png',
      titulo: '“El muerto se fue de rumba” (1987)',
      descripcion: 'El título condensa la picardía que atraviesa buena parte de la obra de Melcochita. Forma parte de sus registros salseros y de una carrera musical sostenida durante décadas.',
      spotify: 'spotify:album:3YKIQvIj5E5tBF3SLEPUfM'
    },
    {
      cover: './img/portada-disco-7.png',
      titulo: '“Mis mejores éxitos” (1997)',
      descripcion: 'Una recopilación de temas representativos de su trayectoria musical. Permite recorrer la faceta de Melcochita como cantante y sonero, muchas veces eclipsada por su fama como humorista.',
      spotify: 'spotify:album:5GSij9Rfgix7qNL07F7bVV'
    },
    {
      cover: './img/portada-disco-8.png',
      titulo: '“El sonero llegó” (2025)',
      descripcion: 'Tras 25 años sin grabar un disco de estudio, regresó con este álbum de 12 canciones. Reinterpreta clásicos de la salsa y busca acercar ese repertorio a nuevas generaciones.',
      spotify: 'spotify:album:213wsPsOqDJoPmTG2BgJeu'
    }
    /* ,{ cover:'./img/portada-disco-5.jpg', titulo:'"..." (año)', descripcion:'...', spotify:'spotify:album:XXXX' } */
  ];

  const ICON_PLAY  = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>';
  const ICON_PAUSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>';

  const track = document.getElementById('discoTrack');
  if (!track) return;

  const cards = []; // { el, btn, index }

  /* ---------- 2. RENDER DE TARJETAS ---------- */
  ALBUMES.forEach(function (album, i) {
    const alt = album.titulo.replace(/"/g, '');
    const card = document.createElement('article');
    card.className = 'disco-card';
    card.innerHTML =
      '<div class="disco-media">' +
        '<div class="disco-vinyl" style="--label:url(\'' + album.cover + '\')"></div>' +
        '<div class="disco-cover">' +
          '<img src="' + album.cover + '" alt="Portada de ' + alt + '" draggable="false" ' +
               'onerror="this.classList.add(\'is-missing\')">' +
        '</div>' +
        '<button class="disco-play" type="button" aria-label="Reproducir ' + alt + '">' +
          '<span class="ico-play">' + ICON_PLAY + '</span>' +
          '<span class="ico-pause">' + ICON_PAUSE + '</span>' +
        '</button>' +
        '<div class="embed-holder"><div class="embed-slot"></div></div>' +
      '</div>' +
      '<h3 class="disco-title">' + album.titulo + '</h3>' +
      '<p class="disco-desc">' + album.descripcion + '</p>';

    track.appendChild(card);
    cards.push({ el: card, btn: card.querySelector('.disco-play'), index: i });
  });

  /* ---------- 3. SPOTIFY IFRAME API ---------- */
  var spotifyAPI = null;
  var pending = [];
  var controllers = new Map(); // index -> controller

  window.onSpotifyIframeApiReady = function (IFrameAPI) {
    spotifyAPI = IFrameAPI;
    pending.forEach(function (fn) { fn(IFrameAPI); });
    pending = [];
  };

  function handlePlayback(index, data) {
    var playing = !data.isPaused;
    cards[index].el.classList.toggle('is-playing', playing);
    // Regla clave: si este álbum empieza a sonar, pausa todos los demás.
    if (playing) {
      controllers.forEach(function (ctrl, i) {
        if (i !== index) ctrl.pause();
      });
    }
  }

  function ensureController(index, autoplay) {
    if (controllers.has(index)) {
      if (autoplay) controllers.get(index).togglePlay();
      return;
    }
    var make = function (API) {
      var slot = cards[index].el.querySelector('.embed-slot');
      API.createController(slot, {
        uri: ALBUMES[index].spotify,
        width: '100%',
        height: '80'
      }, function (controller) {
        controllers.set(index, controller);
        controller.addListener('playback_update', function (e) {
          handlePlayback(index, e.data);
        });
        if (autoplay) controller.play();
      });
    };
    if (spotifyAPI) make(spotifyAPI);
    else pending.push(make);
  }

  /* ---------- 4. CLICK EN PLAY ---------- */
  cards.forEach(function (card) {
    card.btn.addEventListener('click', function () {
      if (dragMoved) return;               // fue arrastre, no click real
      card.el.classList.add('is-open');    // revela el reproductor
      ensureController(card.index, true);  // crea (si hace falta) y alterna play/pausa
    });
  });

  /* ---------- 5. FLECHAS DE NAVEGACIÓN ---------- */
  function step() {
    if (!cards.length) return track.clientWidth;
    var r = cards[0].el.getBoundingClientRect();
    var gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap || 0) || 0;
    return r.width + gap;
  }
  var prev = document.querySelector('.disco-arrow.prev');
  var next = document.querySelector('.disco-arrow.next');
  if (prev) prev.addEventListener('click', function () {
    track.scrollBy({ left: -step(), behavior: 'smooth' });
  });
  if (next) next.addEventListener('click', function () {
    track.scrollBy({ left: step(), behavior: 'smooth' });
  });

  function updateArrows() {
    if (!prev || !next) return;
    var max = track.scrollWidth - track.clientWidth - 1;
    prev.classList.toggle('is-disabled', track.scrollLeft <= 0);
    next.classList.toggle('is-disabled', track.scrollLeft >= max);
  }
  track.addEventListener('scroll', updateArrows, { passive: true });
  window.addEventListener('resize', updateArrows);
  updateArrows();

  /* ---------- 6. ARRASTRE CON CURSOR (solo mouse) ---------- */
  var isDown = false, startX = 0, startScroll = 0, dragMoved = false;

  track.addEventListener('pointerdown', function (e) {
    if (e.pointerType !== 'mouse') return; // táctil usa scroll nativo
    isDown = true;
    dragMoved = false;
    startX = e.clientX;
    startScroll = track.scrollLeft;
    track.classList.add('is-grabbing');
  });
  window.addEventListener('pointermove', function (e) {
    if (!isDown) return;
    var dx = e.clientX - startX;
    if (Math.abs(dx) > 6) dragMoved = true;
    track.scrollLeft = startScroll - dx;
  });
  window.addEventListener('pointerup', function () {
    if (!isDown) return;
    isDown = false;
    track.classList.remove('is-grabbing');
    setTimeout(function () { dragMoved = false; }, 0);
  });
  track.addEventListener('click', function (e) {
    if (dragMoved) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  // Rueda del mouse -> scroll horizontal
  track.addEventListener('wheel', function (e) {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
      track.scrollLeft += e.deltaY;
      e.preventDefault();
    }
  }, { passive: false });
})();
