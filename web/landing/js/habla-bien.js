/* ============================================================
   ¡HABLA BIEN! — Filtros + reproducción aleatoria de audios
   - 2 botones primarios (Frases / Chistes) revelan subsecciones.
   - Cada subsección corresponde a una subcarpeta de ./audio/.
   - "Seleccionar" elige un .mp3 AL AZAR y muestra el reproductor
     con el resultado (play/pausa, progreso, tiempo, seek).
   - Un solo audio a la vez (no se solapa).
   ============================================================ */
(function () {
  'use strict';

  /* ---------- CONFIG ----------
     Para agregar audios: suéltalos en la subcarpeta y añade el
     nombre del archivo a la lista "files" correspondiente. */
  var BASE = 'https://nuevasnarrativasec.github.io/melcochita/web/landing/audio/';
  var DATA = {
    frases: {
      label: 'Frases',
      subs: [
        { id: 'consejos',    label: 'Un consejo',    color: 'amarillo', files: ['frase-8.mp3', 'frase-9.mp3'] },
        { id: 'inspiracion', label: 'Inspírate',     color: 'rosa',     files: ['frase-3.mp3', 'frase-5.mp3', 'frase-6.mp3', 'frase-7.mp3'] },
        { id: 'positivo',    label: '100% positivo', color: 'morado',   files: ['frase-1.mp3', 'frase-10.mp3', 'frase-2.mp3', 'frase-4.mp3'] }
      ]
    },
    chistes: {
      label: 'Chistes',
      subs: [
        { id: 'a-lo-loco', label: 'A lo loco', color: 'amarillo', files: ['descuartizado.mp3', 'loco.mp3', 'locos-venden.mp3'] },
        { id: 'inocente',  label: 'Inocente',  color: 'rosa',     files: ['abuelo.mp3', 'yo-yo.mp3'] },
        { id: 'picante',   label: 'Picante',   color: 'morado',   files: ['feo.mp3', 'sin-amigos.mp3'] }
      ]
    }
  };

  var card = document.querySelector('.frases-card');
  if (!card) return;

  var primaryBtns = card.querySelectorAll('.fp-btn');
  var subsBox     = card.querySelector('.frases-subs');
  var sublabel    = card.querySelector('#frasesSublabel');
  var pillsBox    = card.querySelector('#frasesPills');
  var audio       = card.querySelector('#frasesAudio');

  // Reproductor
  var player = card.querySelector('#frasesPlayer');
  var plCat  = card.querySelector('#fplCat');
  var plTog  = card.querySelector('#fplToggle');
  var plCur  = card.querySelector('#fplCur');
  var plDur  = card.querySelector('#fplDur');
  var plBar  = card.querySelector('#fplBar');
  var plFill = card.querySelector('#fplFill');

  var state = { cat: null, sub: null };

  /* ---------- 1. Botones primarios ---------- */
  primaryBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var cat = btn.getAttribute('data-cat');
      primaryBtns.forEach(function (b) { b.classList.toggle('is-active', b === btn); });
      state.cat = cat;
      state.sub = null;
      renderSubs(cat);
      subsBox.hidden = false;
      // al cambiar de categoría, ocultamos el reproductor anterior
      audio.pause();
      player.hidden = true;
    });
  });

  /* ---------- 2. Render de subsecciones ---------- */
  function renderSubs(cat) {
    var data = DATA[cat];
    sublabel.textContent = data.label + ':';
    pillsBox.className = 'frases-pills' + (cat === 'chistes' ? ' is-chistes' : '');
    pillsBox.innerHTML = '';
    data.subs.forEach(function (sub) {
      var pill = document.createElement('button');
      pill.type = 'button';
      pill.className = 'frases-pill pill-' + sub.color;
      pill.textContent = sub.label;
      pill.setAttribute('data-sub', sub.id);
      pill.addEventListener('click', function () {
        state.sub = sub.id;
        pillsBox.querySelectorAll('.frases-pill').forEach(function (p) {
          p.classList.toggle('is-active', p === pill);
        });
        // Al tocar la opción se reproduce y se muestra el player de una vez.
        // (Tocar de nuevo la misma opción da otro audio al azar.)
        reproducirSub(sub);
      });
      pillsBox.appendChild(pill);
    });
  }

  /* ---------- 3. Elegir audio al azar + reproducir ---------- */
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

  function currentSub() {
    if (!state.cat) return null;
    var subs = DATA[state.cat].subs;
    if (state.sub) {
      for (var i = 0; i < subs.length; i++) if (subs[i].id === state.sub) return subs[i];
    }
    return pick(subs); // sin subsección elegida -> cualquiera de la categoría
  }

  function reproducirSub(sub) {
    if (!sub || !sub.files.length) return;

    var file = pick(sub.files);
    var src  = BASE + state.cat + '/' + sub.id + '/' + file;

    // Un solo audio a la vez.
    audio.pause();
    audio.src = encodeURI(src);
    audio.currentTime = 0;

    // Muestra el reproductor con el resultado
    plCat.textContent = DATA[state.cat].label + ' · ' + sub.label;
    plFill.style.width = '0%';
    plCur.textContent = '0:00';
    plDur.textContent = '0:00';
    player.hidden = false;

    var p = audio.play();
    if (p && p.catch) p.catch(function () {});
  }

  /* ---------- 4. Controles del reproductor ---------- */
  function fmt(t) {
    if (!isFinite(t) || t < 0) t = 0;
    var m = Math.floor(t / 60);
    var s = Math.floor(t % 60);
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  plTog.addEventListener('click', function () {
    if (audio.paused) { var p = audio.play(); if (p && p.catch) p.catch(function () {}); }
    else audio.pause();
  });

  audio.addEventListener('play',  function () { player.classList.add('is-playing'); });
  audio.addEventListener('pause', function () { player.classList.remove('is-playing'); });
  audio.addEventListener('ended', function () {
    player.classList.remove('is-playing');
    plFill.style.width = '100%';
  });
  audio.addEventListener('loadedmetadata', function () { plDur.textContent = fmt(audio.duration); });
  audio.addEventListener('timeupdate', function () {
    plCur.textContent = fmt(audio.currentTime);
    if (audio.duration) plFill.style.width = (audio.currentTime / audio.duration * 100) + '%';
  });

  // Seek al hacer clic/arrastrar en la barra
  function seek(e) {
    var r = plBar.getBoundingClientRect();
    var x = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
    var ratio = Math.min(1, Math.max(0, x / r.width));
    if (audio.duration) audio.currentTime = ratio * audio.duration;
  }
  plBar.addEventListener('click', seek);
  plBar.addEventListener('pointerdown', function (e) {
    seek(e);
    var move = function (ev) { seek(ev); };
    var up = function () {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  });
})();
