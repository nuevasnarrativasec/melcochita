/* ============================================================
   CONOCE A PABLO VILLANUEVA — Carrusel (solo móvil)
   - En móvil, las 3 tarjetas se vuelven un slider horizontal con
     scroll-snap: swipe nativo + flechas amarillas de navegación.
   - En desktop las flechas/hint se ocultan por CSS y la lista se
     muestra como siempre; este script no estorba.
   ============================================================ */
(function () {
  'use strict';

  var carousel = document.querySelector('.conoce-carousel');
  if (!carousel) return;
  var track = carousel.querySelector('ul');
  if (!track) return;
  var prev = carousel.querySelector('.conoce-arrow.prev');
  var next = carousel.querySelector('.conoce-arrow.next');

  function step() {
    var li = track.querySelector('li');
    if (!li) return track.clientWidth;
    var r = li.getBoundingClientRect();
    var gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap || 0) || 0;
    return r.width + gap;
  }

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
})();
