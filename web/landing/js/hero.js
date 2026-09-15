/* ============================================================
   HERO — Intro de audio, reproducción del video y botón flotante
   - Overlay "Activa tu audio" al cargar: botón de audio (activa y
     reproduce desde el inicio) + botón cerrar.
   - btn-audio (esquina) alterna audio on/off.
   - El video se pausa al salir del hero y se reanuda al volver.
   - El botón rojo "melcochea a tu pata" aparece fijo arriba-derecha
     cuando se sale del hero y acompaña toda la landing.
   ============================================================ */
(function () {
  'use strict';

  var video = document.getElementById('heroVideo');
  if (!video) return;

  var cornerBtn = document.querySelector('.btn-audio');
  var hero      = document.querySelector('.hero') || video;
  var intro     = document.getElementById('introAudio');
  var introBtn  = document.getElementById('introAudioBtn');
  var introX    = document.getElementById('introClose');
  var floatBtn  = document.getElementById('btnFlotanteRojo');

  var userPaused = false;

  function safePlay() {
    var p = video.play();
    if (p && p.catch) p.catch(function () {});
  }

  // Estado de audio centralizado (video + botón de esquina)
  function setAudio(on, restart) {
    video.muted = !on;
    if (on) {
      if (restart) video.currentTime = 0;
      userPaused = false;
      safePlay();
    }
    if (cornerBtn) {
      cornerBtn.classList.toggle('is-audio-on', on);
      cornerBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
  }

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
    var toggle = function () { setAudio(video.muted, video.muted); };
    cornerBtn.addEventListener('click', toggle);
    cornerBtn.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
  }

  /* ---------- 3. Viewport: pausar video + botón flotante ---------- */
  function fueraDelHero(fuera) {
    if (fuera) {
      video.pause();
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
})();
