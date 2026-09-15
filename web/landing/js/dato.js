/* ============================================================
   ¡NO LO APRIETES! — Botón por sección que abre un dato de
   Melcochita en una ventana emergente (modal) con cerrar.
   ============================================================ */
(function () {
  'use strict';

  /* Datos (edita/añade libremente). El primer fragmento en <strong>
     sale resaltado en amarillo. */
  var DATOS = [
    '<strong>Antes de Melcochita fue Pacocha.</strong> En los años cincuenta utilizó ese apelativo cuando integraba Son Cubillas. Más tarde, Augusto Ferrando fue clave en el nacimiento del nombre artístico con el que se hizo famoso.',
    '<strong>Trabajó en una joyería antes de vivir de la música.</strong> Según contó, el ácido utilizado en ese oficio le dañó las manos. Después, uno de sus hermanos le enseñó a tocar la conga y su historia tomó otro rumbo.',
    '<strong>Llegó a la televisión casi por casualidad.</strong> Su camino estaba encaminado hacia la música hasta que Augusto Ferrando descubrió que aquel percusionista también podía imitar, contar chistes y conquistar al público.',
    '<strong>En 1983 llegó al programa de David Letterman.</strong> Su aparición en la televisión estadounidense se convirtió en uno de los episodios más singulares de una carrera que ya había traspasado las fronteras peruanas.',
    '<strong>Su gran sueño sigue pendiente en el Perú.</strong> Después de cantar en escenarios internacionales, ha confesado que todavía desea ofrecer un espectáculo como sonero en el Gran Teatro Nacional.'
  ];

  var modal    = document.getElementById('datoModal');
  var textEl   = document.getElementById('datoText');
  var closeBtn = document.getElementById('datoClose');
  if (!modal || !textEl) return;

  function abrir(i) {
    textEl.innerHTML = DATOS[i] || DATOS[0];
    modal.hidden = false;
    document.body.style.overflow = 'hidden'; // bloquea scroll de fondo
  }
  function cerrar() {
    modal.hidden = true;
    document.body.style.overflow = '';
  }

  document.querySelectorAll('.btn-apretar').forEach(function (btn) {
    var i = parseInt(btn.getAttribute('data-dato'), 10) || 0;
    btn.style.cursor = 'pointer';
    btn.addEventListener('click', function () { abrir(i); });
    btn.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(i); }
    });
  });

  if (closeBtn) closeBtn.addEventListener('click', cerrar);
  // cerrar al hacer clic en el fondo oscuro
  modal.addEventListener('click', function (e) { if (e.target === modal) cerrar(); });
  // cerrar con Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !modal.hidden) cerrar();
  });
})();
