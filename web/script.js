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

let ultimosDatos = null;
let enVuelo = false;

// --- Mensajes de carga (progresión lúdica mientras Melcochita "piensa") ---
const MENSAJES_CARGA = [
  "Analizando a la víctima...",
  "Uy, ya le encontré algo...",
  "A ver esa cara...",
  "Esto se está poniendo feo...",
];
const MENSAJE_REVELACION = "Ya salió, ¡imbécil!";
let _cargaTimer = null;

function detenerMensajesCarga() {
  if (_cargaTimer) {
    clearInterval(_cargaTimer);
    _cargaTimer = null;
  }
}

function iniciarMensajesCarga() {
  detenerMensajesCarga();
  let i = 0;
  textoCargando.textContent = MENSAJES_CARGA[0];
  // Avanza por los mensajes y se queda en el último mientras siga cargando.
  _cargaTimer = setInterval(() => {
    i = Math.min(i + 1, MENSAJES_CARGA.length - 1);
    textoCargando.textContent = MENSAJES_CARGA[i];
  }, 1200);
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
      body: JSON.stringify({ ...datos, origen }),
    });

    if (!respuesta.ok) {
      throw new Error("respuesta no OK");
    }

    const data = await respuesta.json();

    // Remate de la carga antes de revelar la chapa.
    detenerMensajesCarga();
    textoCargando.textContent = MENSAJE_REVELACION;
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
