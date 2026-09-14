// Melcochómetro — frontend mínimo (sin framework, sin dependencias externas).
// Nunca maneja ni ve la API key de OpenAI: solo llama a POST /generar, /voz y
// /feedback en el mismo origen. No usa cookies de seguimiento.

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
const btnCompartir = document.getElementById("btn-compartir");

let ultimosDatos = null;
let enVuelo = false;
let _blobMelco = null; // MP3 de la chapa (para compartir/descargar)
let _urlChapa = null;  // objectURL de la chapa (para re-escuchar)

// --- Frases de carga (mientras Melcochita "piensa") ---
const MENSAJES_CARGA = [
  "Analizando a la víctima...",
  "Uy, ya le encontré algo...",
  "A ver esa cara...",
  "Esto se está poniendo feo...",
];
const MENSAJE_REVELACION = "Ya salió, ¡imbécil!";

const AUDIO_CARGA_DIR = "audio-carga";
const AUDIOS_CARGA = [
  "analizando-a-la-victima.mp3",
  "uy-ya-le-encontre-algo.mp3",
  "a-ver-esa-cara.mp3",
  "esto-se-esta-poniendo-feo.mp3",
];
const AUDIO_REVELACION_FILE = "ya-salio-imbecil.mp3";

// Intros PREGRABADOS con la voz real de Melcochita (servidos en /audio-intro).
const AUDIO_INTRO_DIR = "audio-intro";
const AUDIOS_INTRO = [
  "frase-mi-querido.mp3",
  "frase-fuera-oye.mp3",
];

// ======================================================================
// Reproductor de audio ÚNICO — clave para iOS.
// iOS solo deja sonar audio en un elemento "desbloqueado" por un gesto del
// usuario. Usamos UN SOLO <audio> para TODA la secuencia (carga → revelación
// → intro → chapa). Su PRIMERA reproducción ocurre dentro del clic (submit),
// lo que desbloquea el elemento para el resto de clips, aunque lleguen
// después de esperas asíncronas (fetch). Crear un Audio nuevo por clip —como
// antes— hacía que iOS bloqueara todo lo posterior al gesto.
// ======================================================================
const reproductor = new Audio();
reproductor.preload = "auto";
reproductor.setAttribute("playsinline", "");
let _resolverClip = null;

function _reproducir(src) {
  // Si había un clip en curso esperando, lo resolvemos (cambio de clip).
  if (_resolverClip) { const r = _resolverClip; _resolverClip = null; r(); }
  return new Promise((resolve) => {
    _resolverClip = resolve;
    const finalizar = () => {
      if (_resolverClip === resolve) { _resolverClip = null; resolve(); }
    };
    reproductor.onended = finalizar;
    try {
      reproductor.src = src;
      reproductor.currentTime = 0;
      const p = reproductor.play();
      if (p && p.catch) p.catch(finalizar); // bloqueado/errores: seguimos igual
    } catch (_) {
      finalizar();
    }
  });
}

function _detenerReproductor() {
  try { reproductor.pause(); } catch (_) {}
  reproductor.onended = null;
  if (_resolverClip) { const r = _resolverClip; _resolverClip = null; r(); }
}

// --- Secuencia de carga (frases + audio) ---
let _cargando = false;

async function iniciarMensajesCarga() {
  // OJO: se llama SIN await desde el gesto de submit; su primer _reproducir
  // se ejecuta sincrónicamente dentro del clic y desbloquea el audio en iOS.
  _cargando = true;
  for (let i = 0; i < MENSAJES_CARGA.length; i++) {
    if (!_cargando) return;
    textoCargando.textContent = MENSAJES_CARGA[i];
    await _reproducir(`${AUDIO_CARGA_DIR}/${AUDIOS_CARGA[i]}`);
  }
  // Se acabaron las frases pero sigue generando: queda la última en pantalla.
  if (_cargando) textoCargando.textContent = MENSAJES_CARGA[MENSAJES_CARGA.length - 1];
}

function detenerMensajesCarga() {
  _cargando = false;
  _detenerReproductor();
}

// --- Secuencia de revelación: "¡Ya salió!" → intro grabado → chapa ---
async function secuenciaRevelacion(texto) {
  await _reproducir(`${AUDIO_CARGA_DIR}/${AUDIO_REVELACION_FILE}`);
  if (AUDIOS_INTRO.length) {
    const archivo = AUDIOS_INTRO[Math.floor(Math.random() * AUDIOS_INTRO.length)];
    await _reproducir(`${AUDIO_INTRO_DIR}/${archivo}`);
  }
  await reproducirChapa(texto);
}

// --- Voz de la chapa (pedida a /voz, PELADA: el "Mi querido" lo da el intro) ---
async function reproducirChapa(texto) {
  if (btnEscuchar) btnEscuchar.hidden = true;
  if (btnCompartir) btnCompartir.hidden = true;
  _blobMelco = null;
  if (_urlChapa) { URL.revokeObjectURL(_urlChapa); _urlChapa = null; }
  try {
    const r = await fetch("/voz", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto }),
    });
    if (!r.ok) return; // sin audio (p.ej. voz no configurada): la chapa se ve igual
    const blob = await r.blob();
    _blobMelco = blob;
    _urlChapa = URL.createObjectURL(blob);
    if (btnEscuchar) btnEscuchar.hidden = false;
    if (btnCompartir) btnCompartir.hidden = false;
    await _reproducir(_urlChapa); // mismo elemento ya desbloqueado
  } catch (err) {
    /* el audio es un plus; nunca interrumpe la experiencia */
  }
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
  iniciarMensajesCarga(); // fire-and-forget: primer audio en-gesto (desbloquea iOS)

  try {
    const respuesta = await fetch("/generar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // ultima_chapa: para que el motor v3 no repita la misma chapa original.
      body: JSON.stringify({ ...datos, origen, ultima_chapa: textoChapa.textContent || "" }),
    });

    if (!respuesta.ok) {
      throw new Error("respuesta no OK");
    }

    const data = await respuesta.json();

    detenerMensajesCarga();
    textoCargando.textContent = MENSAJE_REVELACION;
    secuenciaRevelacion(data.chapa); // fire-and-forget: "¡Ya salió!" → intro → chapa

    await new Promise((r) => setTimeout(r, 600)); // beat dramático antes de mostrar

    textoChapa.textContent = data.chapa;
    reiniciarFeedbackUI();
    mostrarSolo(tarjetaResultado);
  } catch (err) {
    detenerMensajesCarga();
    mostrarSolo(tarjetaError);
  } finally {
    enVuelo = false;
  }
}

if (btnEscuchar) {
  btnEscuchar.addEventListener("click", () => {
    if (_urlChapa) _reproducir(_urlChapa);
  });
}

// --- Compartir la chapa en audio ---
// Móvil: compartir nativo con el MP3 adjunto (el enlace va DENTRO del texto,
// sin el campo `url` aparte, que hace colgar a WhatsApp). Escritorio: descarga.
async function compartirChapa() {
  if (!_blobMelco) return;
  const archivo = new File([_blobMelco], "melcochita.mp3", { type: "audio/mpeg" });
  const enlace = window.location.origin;
  const texto = `Melcochita me chapó: "${textoChapa.textContent}" 😂 Hazte el tuyo: ${enlace}`;

  const esTactil = (navigator.maxTouchPoints || 0) > 0 || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  const puedeArchivo = navigator.canShare && navigator.canShare({ files: [archivo] });

  if (esTactil && puedeArchivo) {
    try {
      await navigator.share({ files: [archivo], text: texto });
      return;
    } catch (err) {
      if (err && err.name === "AbortError") return; // el usuario canceló
      // cualquier otro error: caemos a descarga
    }
  }

  // Escritorio o sin soporte de compartir archivos: descargar el MP3.
  const a = document.createElement("a");
  a.href = _urlChapa || URL.createObjectURL(_blobMelco);
  a.download = "melcochita.mp3";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

if (btnCompartir) {
  btnCompartir.addEventListener("click", compartirChapa);
}

async function enviarFeedback(valor) {
  // "Fire and forget": no bloquea ni depende de la respuesta.
  try {
    await fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ valor }),
    });
  } catch (err) {
    /* el feedback es opcional; no interrumpe la experiencia */
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
if (window.parent && window.parent !== window) {
  const _postAlto = () => {
    const alto = Math.ceil(document.documentElement.scrollHeight);
    window.parent.postMessage({ tipo: "melco-alto", alto: alto }, "*");
  };
  window.addEventListener("load", _postAlto);
  if (window.ResizeObserver) {
    new ResizeObserver(_postAlto).observe(document.body);
  } else {
    setInterval(_postAlto, 500);
  }
}
