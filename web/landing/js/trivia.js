/* ============================================================
   APURA OYE — Trivia "¿Cuánto conoces a Melcochita?"
   - 8 preguntas (A/B/C). Al elegir una opción (correcta o no)
     se bloquea, se marca la correcta y aparece la explicación
     en texto amarillo.
   - "Siguiente" avanza; al final muestra el resultado según los
     aciertos (0-2, 3-5, 6-8) con "Volver a jugar".
   ============================================================ */
(function () {
  'use strict';

  var PREGUNTAS = [
    {
      q: 'Antes de ser "Melcochita", Pablo Villanueva ya tenía otra chapa artística. ¿Cuál era?',
      o: ['Pacocha', 'Karamanduka', 'Sonero Pablo'], c: 0,
      e: 'Antes de hacerse famoso como Melcochita, en los años cincuenta se hacía llamar Pacocha mientras integraba Son Cubillas.'
    },
    {
      q: 'Antes de vivir de la música y el humor, Melcochita tuvo un oficio bastante alejado del escenario. ¿Cuál fue?',
      o: ['Trabajó en una imprenta', 'Trabajó en una joyería', 'Trabajó en una barbería'], c: 1,
      e: 'Trabajó en una joyería y ha contado que el ácido utilizado en ese oficio terminó dañando sus manos.'
    },
    {
      q: 'Melcochita empezó con la música desde niño. ¿Sabes qué grupo integró cuando tenía seis años?',
      o: ['Son Cubillas', 'Son de Aruba', 'Mag Peruvian All Stars'], c: 1,
      e: 'Su relación con la música empezó desde niño: a los seis años integró Son de Aruba. Más adelante formaría Son Cubillas junto a sus hermanos.'
    },
    {
      q: 'Melcochita dejó su huella en el rock peruano. ¿En cuál de estos discos participó tocando percusión?',
      o: ['Picardías de Melcochita', 'Virgin de Traffic Sound', 'La estrella del son'], c: 1,
      e: 'En 1969 participó en Virgin, el primer disco de Traffic Sound, aportando en la percusión con las congas de la emblemática canción "Meshkalina".'
    },
    {
      q: '¿Con quién grabó Melcochita La estrella del son?',
      o: ['Willie Colón', 'Johnny Pacheco', 'Tito Puente'], c: 1,
      e: 'La estrella del son apareció en 1989 y lo conectó directamente con Johnny Pacheco, una de las figuras centrales de la salsa internacional. Además, Pacheco asumió la producción del disco en Nueva York.'
    },
    {
      q: 'En 1983 Melcochita llegó a la televisión estadounidense. ¿En qué programa apareció?',
      o: ['Late Night with David Letterman', 'Saturday Night Live', 'The Tonight Show'], c: 0,
      e: 'Melcochita apareció con David Letterman en 1983, en un segmento llamado "International Night", uno de los episodios más insólitos de su carrera internacional.'
    },
    {
      q: '¿Cómo nació el famoso "¡No vayan!"?',
      o: [
        'Lo improvisó para despedir al público al final de un show.',
        'Lo dijo para bromear con la invitación de otro humorista.',
        'Se le escapó durante una publicidad en televisión.'
      ], c: 1,
      e: 'Miguel Barraza estaba invitando al público a visitar su cebichería cuando Melcochita, bajito y para fastidiarlo, soltó un "no vayan". La ocurrencia terminó convirtiéndose en una de sus frases más reconocibles.'
    },
    {
      q: 'A sus 90 años, ¿qué sueño como sonero sigue pendiente?',
      o: ['Grabar un disco con Willie Colón', 'Dar un espectáculo en el Gran Teatro Nacional', 'Volver a cantar en Nueva York'], c: 1,
      e: 'Después de décadas de carrera, Melcochita ha dicho que todavía quiere presentarse como sonero en el Gran Teatro Nacional.'
    }
  ];

  var NIVELES = [
    { min: 0, max: 2, titulo: 'Aprendiz de Melcocha', desc: 'Conoces al Melcochita que todos hemos visto y escuchado, pero todavía hay bastante por descubrir detrás de sus chapas, su música y sus historias.' },
    { min: 3, max: 5, titulo: 'Melcocha sonero',      desc: 'Sabes que Melcochita es mucho más que el cómico de la tele. Entre salsa, rock, chapas y escenarios internacionales, no te agarra tan fácil.' },
    { min: 6, max: 8, titulo: 'Melcocha Lover',        desc: 'Lo tuyo ya no es solo "¡No vayan!". Conoces a Pacocha, al sonero, al cómico y hasta esas historias que muchos no tenían en el radar.' }
  ];

  var LETRAS = ['A', 'B', 'C'];

  var cont = document.getElementById('trivia');
  if (!cont) return;

  var idx = 0, score = 0, answered = false;

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderPregunta() {
    var p = PREGUNTAS[idx];
    var opts = '';
    p.o.forEach(function (txt, i) {
      opts += '<button class="tc-opt" type="button" data-i="' + i + '">' +
                '<span class="tc-letter">' + LETRAS[i] + '</span>' +
                '<span class="tc-opt-txt">' + esc(txt) + '</span>' +
              '</button>';
    });
    cont.innerHTML =
      '<div class="trivia-card">' +
        '<span class="tc-corner tc-tr"></span><span class="tc-corner tc-bl"></span>' +
        '<p class="tc-progress">' + (idx + 1) + '/' + PREGUNTAS.length + '</p>' +
        '<p class="tc-question">' + esc(p.q) + '</p>' +
        '<div class="tc-options">' + opts + '</div>' +
        '<p class="tc-explain" hidden></p>' +
        '<button class="tc-next" type="button" disabled>Siguiente</button>' +
      '</div>';

    answered = false;
    var optBtns = cont.querySelectorAll('.tc-opt');
    optBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (answered) return;
        answered = true;
        var chosen = parseInt(btn.getAttribute('data-i'), 10);
        optBtns.forEach(function (b) {
          var bi = parseInt(b.getAttribute('data-i'), 10);
          b.disabled = true;
          if (bi === p.c) b.classList.add('is-correct');
          else if (bi === chosen) b.classList.add('is-wrong');
        });
        if (chosen === p.c) score++;
        var ex = cont.querySelector('.tc-explain');
        ex.textContent = p.e;           // explicación / respuesta correcta en amarillo
        ex.hidden = false;
        cont.querySelector('.tc-next').disabled = false;
      });
    });

    cont.querySelector('.tc-next').addEventListener('click', function () {
      if (!answered) return;
      idx++;
      if (idx >= PREGUNTAS.length) renderResultado();
      else renderPregunta();
    });
  }

  function nivelDe(s) {
    for (var i = 0; i < NIVELES.length; i++) {
      if (s >= NIVELES[i].min && s <= NIVELES[i].max) return NIVELES[i];
    }
    return NIVELES[NIVELES.length - 1];
  }

  function renderResultado() {
    var n = nivelDe(score);
    cont.innerHTML =
      '<div class="trivia-card result">' +
        '<span class="tc-corner tc-tr"></span><span class="tc-corner tc-bl"></span>' +
        '<img class="tc-face" src="./img/cara-resultado-1.png" alt="Melcochita">' +
        '<p class="tc-eres">Eres un</p>' +
        '<h3 class="tc-title">' + esc(n.titulo) + '</h3>' +
        '<p class="tc-desc">' + esc(n.desc) + '</p>' +
        '<button class="tc-replay" type="button">Volver a jugar</button>' +
      '</div>';
    cont.querySelector('.tc-replay').addEventListener('click', function () {
      idx = 0; score = 0; renderPregunta();
    });
  }

  renderPregunta();
})();
