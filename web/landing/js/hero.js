/* ============================================================
   HERO — Intro de audio, reproducción del video y botón flotante
   - Dos videos: #heroVideo (desktop) y #heroVideoMovil (móvil). El CSS
     muestra uno u otro según el breakpoint (640px). El audio se aplica
     SIEMPRE al video ACTIVO; el inactivo queda mute y en pausa, así nunca
     suenan los dos a la vez. Al cambiar de breakpoint, el audio se
     transfiere al nuevo video activo sin reiniciar.
   - Overlay "Activa tu audio" al cargar: botón (activa y reproduce desde
     el inicio) + botón cerrar.
   - btn-audio (esquina) alterna audio on/off.
   - El video se pausa al salir del hero y se reanuda al volver.
   - El botón rojo "melcochea a tu pata" aparece fijo cuando se sale del hero.
   ============================================================ */
(function () {
  'use strict';

  var video      = document.getElementById('heroVideo');      // desktop
  var videoMovil = document.getElementById('heroVideoMovil');  // móvil
  var videos = [video, videoMovil].filter(Boolean);
  if (!videos.length) return;

  var cornerBtn = document.querySelector('.btn-audio');
  var hero      = document.querySelector('.hero') || videos[0];
  var intro     = document.getElementById('introAudio');
  var introBtn  = document.getElementById('introAudioBtn');
  var introX    = document.getElementById('introClose');
  var floatBtn  = document.getElementById('btnFlotanteRojo');

  // Breakpoint que decide qué video se ve (coincide con el CSS: 640px).
  var mqMovil = window.matchMedia('(max-width: 640px)');

  var userPaused = false;
  var audioOn = false; // estado global; se conserva al cambiar de video

  // Video ACTIVO según el viewport.
  function videoActivo() {
    return (mqMovil.matches && videoMovil) ? videoMovil : (video || videoMovil);
  }

  function playEl(v) { if (!v) return; var p = v.play(); if (p && p.catch) p.catch(function () {}); }
  function safePlay() { playEl(videoActivo()); }

  // Aplica el estado de audio al video activo; el resto queda mute + en pausa.
  function aplicarAudio(restart) {
    var act = videoActivo();
    videos.forEach(function (v) {
      if (v === act) {
        v.muted = !audioOn;
        if (audioOn && restart) v.currentTime = 0;
        playEl(v);
      } else {
        v.muted = true;
        try { v.pause(); } catch (e) {}
      }
    });
    if (cornerBtn) {
      cornerBtn.classList.toggle('is-audio-on', audioOn);
      cornerBtn.setAttribute('aria-pressed', audioOn ? 'true' : 'false');
    }
  }

  function setAudio(on, restart) {
    audioOn = on;
    if (on) userPaused = false;
    aplicarAudio(restart);
  }

  // Al cambiar de breakpoint, transfiere el audio al nuevo video activo.
  var onMqChange = function () { aplicarAudio(false); };
  if (mqMovil.addEventListener) mqMovil.addEventListener('change', onMqChange);
  else if (mqMovil.addListener) mqMovil.addListener(onMqChange);

  /* ---------- 1. Overlay de intro ---------- */
  function cerrarIntro() { if (intro) intro.classList.add('is-hidden'); }

  if (introBtn) {
    introBtn.style.cursor = 'pointer';
    introBtn.addEventListener('click', function () {
      setAudio(true, true);   // activa audio y reproduce desde el inicio
      cerrarIntro();
    });
  }
  if (introX) introX.addEventListener('click', cerrarIntro);

  /* ---------- 2. Botón de audio (esquina) ---------- */
  if (cornerBtn) {
    cornerBtn.style.cursor = 'pointer';
    cornerBtn.setAttribute('role', 'button');
    cornerBtn.setAttribute('tabindex', '0');
    cornerBtn.setAttribute('aria-pressed', 'false');
    var toggle = function () { setAudio(!audioOn, !audioOn); };
    cornerBtn.addEventListener('click', toggle);
    cornerBtn.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
  }

  /* ---------- 3. Viewport: pausar video + botón flotante ---------- */
  function fueraDelHero(fuera) {
    if (fuera) {
      videos.forEach(function (v) { try { v.pause(); } catch (e) {} });
      if (floatBtn) floatBtn.classList.add('is-visible');
    } else {
      if (!userPaused) safePlay();
      if (floatBtn) floatBtn.classList.remove('is-visible');
    }
  }

  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { fueraDelHero(e.intersectionRatio < 0.3); });
    }, { threshold: [0, 0.3, 0.6] });
    io.observe(hero);
  } else {
    window.addEventListener('scroll', function () {
      var r = hero.getBoundingClientRect();
      var visible = r.bottom > window.innerHeight * 0.3 && r.top < window.innerHeight * 0.7;
      fueraDelHero(!visible);
    }, { passive: true });
  }

  // Inicial: deja sólo el video activo reproduciéndose (mute), pausa el otro.
  aplicarAudio(false);
})();
