// Melcochómetro — frontend mínimo (sin framework, sin dependencias externas).
// Nunca maneja ni ve la API key de OpenAI: solo llama a POST /generar y
// POST /feedback en el mismo origen. Nunca muestra scoring, patrón,
// operación, prompts, candidatos internos ni información del corpus.
// No usa cookies de seguimiento ni pide datos personales.

const form = document.getElementById("form-chapa");
const btnGenerar = document.getElementById("btn-generar");
const mensajeValidacion = document.getElementById("mensaje-validacion");

const estadoCargando = document.getElementById("estado-cargando");
const textoCargando = document.getElementById("texto-cargando");
const tarjetaResultado = document.getElementById("tarjeta-resultado");
const tarjetaError = document.getElementById("tarjeta-error");
const textoChapa = document.getElementById("texto-chapa");

const btnOtraChapa = document.getElementById("btn-otra-chapa");
const btnMelcochizarOtro = document.getElementById("btn-melcochizar-otro");
const btnReintentar = document.getElementById("btn-reintentar");

const btnMeGusta = document.getElementById("btn-me-gusta");
const btnNoMeGusta = document.getElementById("btn-no-me-gusta");
const mensajeFeedback = document.getElementById("mensaje-feedback");

const btnEscuchar = document.getElementById("btn-escuchar");

let ultimosDatos = null;
let enVuelo = false;
let _audioMelco = null; // último audio de la voz de Melcochita

// --- Mensajes de carga (progresión lúdica mientras Melcochita "piensa") ---
// Cada frase tiene su audio con la voz de Melcochita; el texto avanza a la
// siguiente frase cuando termina su audio (quedándose en la última mientras
// siga cargando). El orden de AUDIOS_CARGA calza con MENSAJES_CARGA.
const MENSAJES_CARGA = [
  "Analizando a la víctima...",
  "Uy, ya le encontré algo...",
  "A ver esa cara...",
  "Esto se está poniendo feo...",
];
const MENSAJE_REVELACION = "Ya salió, ¡imbécil!";

const AUDIO_CARGA_DIR = "audio-carga"; // servido por app.py (ver README)
const AUDIOS_CARGA = [
  "analizando-a-la-victima.mp3",
  "uy-ya-le-encontre-algo.mp3",
  "a-ver-esa-cara.mp3",
  "esto-se-esta-poniendo-feo.mp3",
];
const AUDIO_REVELACION_FILE = "ya-salio-imbecil.mp3";

let _cargaTimer = null;   // fallback por tiempo si el audio no puede sonar
let _audioCarga = null;   // audio de la frase de carga en curso
let _cargando = false;

function _detenerAudioCarga() {
  if (_audioCarga) {
    _audioCarga.onended = null;
    try { _audioCarga.pause(); } catch (_) {}
    _audioCarga = null;
  }
}

function detenerMensajesCarga() {
  _cargando = false;
  if (_cargaTimer) {
    clearInterval(_cargaTimer);
    _cargaTimer = null;
  }
  _detenerAudioCarga();
}

// Fallback sin audio: cicla el texto por tiempo (comportamiento original).
function _ciclarTextoPorTiempo() {
  if (_cargaTimer) return;
  let i = 0;
  textoCargando.textContent = MENSAJES_CARGA[0];
  _cargaTimer = setInterval(() => {
    i = Math.min(i + 1, MENSAJES_CARGA.length - 1);
    textoCargando.textContent = MENSAJES_CARGA[i];
  }, 1200);
}

// Muestra la frase i con su audio; al terminar el audio avanza a la
// siguiente. Si el navegador bloquea el audio, cae al ciclo por tiempo.
function _reproducirFraseCarga(i) {
  if (!_cargando) return;
  textoCargando.textContent = MENSAJES_CARGA[i];
  _detenerAudioCarga();
  const a = new Audio(`${AUDIO_CARGA_DIR}/${AUDIOS_CARGA[i]}`);
  _audioCarga = a;
  a.onended = () => {
    if (!_cargando) return;
    if (i < MENSAJES_CARGA.length - 1) _reproducirFraseCarga(i + 1);
    // en la última frase se queda en pantalla hasta la revelación
  };
  a.play().catch(() => {
    _detenerAudioCarga();
    _ciclarTextoPorTiempo();
  });
}

function iniciarMensajesCarga() {
  detenerMensajesCarga();
  _cargando = true;
  _reproducirFraseCarga(0);
}

function mostrarSolo(el) {
  [form, estadoCargando, tarjetaResultado, tarjetaError].forEach((e) => e.classList.add("oculto"));
  el.classList.remove("oculto");
}

function reiniciarFeedbackUI() {
  btnMeGusta.disabled = false;
  btnNoMeGusta.disabled = false;
  btnMeGusta.classList.remove("votado");
  btnNoMeGusta.classList.remove("votado");
  mensajeFeedback.classList.add("oculto");
}

function leerDatosFormulario() {
  return {
    nombre_o_apodo: document.getElementById("nombre_o_apodo").value.trim(),
    sexo: document.getElementById("sexo").value, // solo concordancia (motor v3)
    caracteristica: document.getElementById("caracteristica").value.trim(),
    costumbre: document.getElementById("costumbre").value.trim(),
    objeto_que_siempre_usa: document.getElementById("objeto_que_siempre_usa").value.trim(),
  };
}

function validar(datos) {
  if (!datos.nombre_o_apodo) {
    return "Cuéntanos cómo le dicen.";
  }
  const otros = [datos.caracteristica, datos.costumbre, datos.objeto_que_siempre_usa];
  const completados = otros.filter((v) => v.length > 0).length;
  if (completados < 2) {
    return "Completa al menos 2 de los otros 3 datos (rasgo físico, costumbre u objeto).";
  }
  return null;
}

async function solicitarChapa(datos, origen) {
  if (enVuelo) return;
  enVuelo = true;
  mostrarSolo(estadoCargando);
  iniciarMensajesCarga();

  try {
    const respuesta = await fetch("/generar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // ultima_chapa: la última mostrada, para que el motor v3 no repita
      // inmediatamente la misma chapa original al pedir "otra chapa".
      body: JSON.stringify({ ...datos, origen, ultima_chapa: textoChapa.textContent || "" }),
    });

    if (!respuesta.ok) {
      throw new Error("respuesta no OK");
    }

    const data = await respuesta.json();

    // Remate de la carga: suena "¡Ya salió, imbécil!" con su audio y, al
    // terminar ese audio, arranca la voz de la chapa (para que no se pisen).
    detenerMensajesCarga();
    textoCargando.textContent = MENSAJE_REVELACION;

    let chapaDisparada = false;
    const dispararChapa = () => {
      if (chapaDisparada) return;
      chapaDisparada = true;
      reproducirVoz(data.chapa); // la voz de Melcochita, con su marco discursivo
    };
    const revelacion = new Audio(`${AUDIO_CARGA_DIR}/${AUDIO_REVELACION_FILE}`);
    revelacion.onended = dispararChapa;
    revelacion.play().catch(dispararChapa); // si no puede sonar, va directo la chapa

    await new Promise((r) => setTimeout(r, 700));

    textoChapa.textContent = data.chapa;
    reiniciarFeedbackUI();
    mostrarSolo(tarjetaResultado);
  } catch (err) {
    // Nunca se muestra el detalle técnico al usuario.
    detenerMensajesCarga();
    mostrarSolo(tarjetaError);
  } finally {
    enVuelo = false;
  }
}

// --- Voz de Melcochita ---
// Pide a /voz el audio de la chapa (el backend le pone el marco "Mi
// querido…") y lo reproduce. Es un plus: si algo falla, la chapa se ve
// igual y no se rompe nada. En pantalla siempre se muestra la chapa
// pelada; lo que suena es la versión enmarcada.
async function reproducirVoz(texto) {
  if (btnEscuchar) btnEscuchar.hidden = true;
  try {
    const r = await fetch("/voz", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto }),
    });
    if (!r.ok) return; // sin audio (p.ej. voz no configurada): la chapa se ve igual
    const blob = await r.blob();
    if (_audioMelco) URL.revokeObjectURL(_audioMelco.src);
    _audioMelco = new Audio(URL.createObjectURL(blob));
    if (btnEscuchar) btnEscuchar.hidden = false;
    _audioMelco.play().catch(() => {}); // si el navegador bloquea autoplay, queda el botón
  } catch (err) {
    /* el audio es opcional; nunca interrumpe la experiencia */
  }
}

if (btnEscuchar) {
  btnEscuchar.addEventListener("click", () => {
    if (_audioMelco) _audioMelco.play();
  });
}

async function enviarFeedback(valor) {
  // "Fire and forget": no bloquea la interfaz ni depende de la respuesta.
  // No se envía la chapa ni ningún dato del formulario, solo el voto.
  try {
    await fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ valor }),
    });
  } catch (err) {
    // Silencioso: el feedback es opcional y no debe interrumpir la experiencia.
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  if (enVuelo) return;

  const datos = leerDatosFormulario();
  const error = validar(datos);

  if (error) {
    mensajeValidacion.textContent = error;
    mensajeValidacion.classList.remove("oculto");
    return;
  }

  mensajeValidacion.classList.add("oculto");
  ultimosDatos = datos;
  btnGenerar.disabled = true;
  btnGenerar.textContent = "MELCOCHEANDO...";
  solicitarChapa(ultimosDatos, "primera").finally(() => {
    btnGenerar.disabled = false;
    btnGenerar.textContent = "¡MELCOCHÉALO!";
  });
});

btnOtraChapa.addEventListener("click", () => {
  if (!ultimosDatos || enVuelo) return;
  btnOtraChapa.disabled = true;
  solicitarChapa(ultimosDatos, "otra_chapa").finally(() => {
    btnOtraChapa.disabled = false;
  });
});

btnMelcochizarOtro.addEventListener("click", () => {
  form.reset();
  mensajeValidacion.classList.add("oculto");
  ultimosDatos = null;
  mostrarSolo(form);
});

btnReintentar.addEventListener("click", () => {
  if (!ultimosDatos || enVuelo) return;
  btnReintentar.disabled = true;
  solicitarChapa(ultimosDatos, "otra_chapa").finally(() => {
    btnReintentar.disabled = false;
  });
});

btnMeGusta.addEventListener("click", () => {
  if (btnMeGusta.disabled) return;
  btnMeGusta.disabled = true;
  btnNoMeGusta.disabled = true;
  btnMeGusta.classList.add("votado");
  mensajeFeedback.classList.remove("oculto");
  enviarFeedback("positivo");
});

btnNoMeGusta.addEventListener("click", () => {
  if (btnNoMeGusta.disabled) return;
  btnMeGusta.disabled = true;
  btnNoMeGusta.disabled = true;
  btnNoMeGusta.classList.add("votado");
  mensajeFeedback.classList.remove("oculto");
  enviarFeedback("negativo");
});

// --- Auto-alto cuando el Melcochómetro va embebido en un iframe ---
// Si la página corre dentro de un iframe (landing de El Comercio), le
// avisa a la página contenedora su altura real para que el iframe crezca
// o encoja según el estado (formulario / cargando / resultado), sin scroll
// interno ni espacios vacíos. En uso normal (no embebido) no hace nada.
if (window.parent && window.parent !== window) {
  const _postAlto = () => {
    const alto = Math.ceil(document.documentElement.scrollHeight);
    window.parent.postMessage({ tipo: "melco-alto", alto: alto }, "*");
  };
  window.addEventListener("load", _postAlto);
  if (window.ResizeObserver) {
    new ResizeObserver(_postAlto).observe(document.body);
  } else {
    setInterval(_postAlto, 500); // fallback para navegadores viejos
  }
}
