// English and Spanish. English is written in the HTML and is the default; Spanish is chosen
// with the EN/ES switch (remembered in this browser) or with `?lang=es` in the address.
// Elements carry `data-i18n` (their content) or `data-i18n-aria` (their aria-label). What
// people say in the example transcript is not translated: it stays as it was spoken.
(function () {
  var ES = {
    pageTitle: "AdVera — Cada reunión, conocimiento verificable",
    pageDescription:
      "AdVera es un gestor de reuniones con IA, libre y de código abierto, que se instala en tus propias máquinas. Todo queda grabado y todo se puede comprobar: cada resumen, decisión y respuesta enlaza con el segundo exacto del audio que la respalda.",
    skip: "Saltar al contenido",
    homeLabel: "AdVera, inicio",
    navLabel: "Secciones",
    langLabel: "Idioma",
    navCapture: "Captura",
    navTranscript: "Transcripción",
    navRecorded: "Qué se graba",
    navBrain: "Brain",
    navHow: "Cómo funciona",
    navInstall: "Instalar",

    heroLabel: "Código abierto · Autoalojado · Gestor de reuniones con IA",
    slogan: "Cada reunión, conocimiento verificable.",
    heroLead:
      "AdVera nace de una idea: <strong>todo queda grabado, y todo se puede comprobar.</strong> Cada resumen, decisión, acción y respuesta enlaza con el segundo exacto del audio que la respalda.",
    heroInstall: "Instalar AdVera",
    heroCode: "Ver el código →",
    brainLabel: "Un cerebro dibujado con miles de pequeños triángulos de colores",

    captureLabel: "Captura",
    captureTitle: "Tres maneras de entrar.",
    captureText:
      "Graba desde el navegador sin instalar nada, deja que el agente de escritorio capture tus llamadas o importa las grabaciones que ya tienes.",
    capture1Title: "Desde el navegador",
    capture1Text: "Graba la reunión con tu micrófono, en la propia aplicación. Sin plugins ni extensiones.",
    capture2Title: "Agente de escritorio",
    capture2Text:
      "En Windows, un pequeño agente graba tu micrófono y el sonido de la llamada como pistas separadas y los envía a tu servidor.",
    capture3Title: "Importar grabaciones",
    capture3Text:
      "Sube un archivo de audio o vídeo que ya tengas. AdVera extrae el audio, lo transcribe y lo añade al Brain como cualquier otra reunión.",
    sourceBrowser: "Navegador",
    sourceAgent: "Agente de escritorio",
    sourceImport: "Importar",
    waveLabel: "La forma de onda de una grabación en curso",
    waveCaption: "Grabando · Reunión semanal",

    transcriptLabel: "Ejemplo de transcripción",
    transcriptCaption: "Whisper · identificación de hablantes",
    transcriptVoices: "6 voces · 3 idiomas",
    transcriptionLabel: "Transcripción",
    transcriptionTitle: "Quién dijo qué, y cuándo.",
    transcriptionText1:
      "Whisper transcribe la grabación en unos 100 idiomas, cada parte en el idioma en que se dijo. La diarización distingue las voces, y tú pones nombre a cada una una sola vez: a partir de ahí, el nombre se usa en todas partes.",
    transcriptionText2:
      "Cada línea conserva su tiempo. Ese tiempo es lo que después convierte una afirmación en algo que puedes comprobar.",

    recordedLabel: "Qué se graba",
    recordedTitle: "Todo queda grabado. Todo se puede comprobar.",
    recordedText:
      "AdVera guarda el audio, la transcripción con quién dijo qué y cuándo, tus notas y lo que la IA concluyó a partir de ellos. Nada es una caja negra.",
    recordedAudio: "El audio",
    recordedAudioText:
      "Las grabaciones conservan sus pistas originales, el micrófono y el sonido del sistema por separado. Un archivo importado conserva su audio.",
    recordedTranscript: "La transcripción",
    recordedTranscriptText:
      "Una transcripción definitiva por reunión, con el hablante, el idioma y el tiempo de cada segmento.",
    recordedNotes: "Tus notas",
    recordedNotesText:
      "Un editor Markdown en cada reunión, con referencias a otras reuniones. Las notas se citan igual que la transcripción.",
    recordedAi: "Lo que hizo la IA",
    recordedAiText:
      "Cada llamada al modelo se guarda con la versión del prompt y su respuesta en bruto. Un elemento sin una cita válida se descarta, no se muestra.",

    answerLabel: "Ejemplo de respuesta con citas",
    answerQuestion: "¿Qué decidimos sobre el almacenamiento?",
    answerText:
      'Ampliar el volumen de almacenamiento esta semana, después de que las copias de seguridad fallaran dos veces<a href="#cited" class="cite">00:12</a>. Marta prepara el informe de costes para el viernes<a href="#cited" class="cite">03:41</a>.',
    answerCaption: "Cada cita abre la reunión y reproduce el momento en que se dijo.",
    citedLabel: "Respuestas con citas",
    citedTitle: "La respuesta, y el segundo en que se dijo.",
    citedText:
      "Pregunta lo que quieras sobre tus reuniones. La respuesta llega con sus fuentes, y cada fuente reproduce el audio en el momento que la respalda. Cuando las reuniones no contienen la respuesta, AdVera lo dice.",

    brainSectionLabel: "El Brain",
    brainTitle: "Una sola memoria de todas tus reuniones.",
    brainText:
      "AdVera transcribe en unos 100 idiomas, distingue quién habla y escribe un resumen de cada reunión. El Brain lo conecta todo.",
    brainSearch: "Búsqueda",
    brainSearchText: "Búsqueda híbrida, por texto y por significado, en todas las reuniones, con respuestas citadas.",
    brainGraph: "Grafo de conceptos",
    brainGraphText: "Personas, proyectos, productos y temas, y cómo se relacionan, a partir de lo que se dijo.",
    brainTimelines: "Líneas de tiempo",
    brainTimelinesText: "Cómo evolucionó un proyecto o un tema, reunión tras reunión, de lo más reciente a lo más antiguo.",
    brainFacts: "Decisiones y acciones",
    brainFactsText:
      "Cada decisión, acción, duda abierta y riesgo de todas las reuniones, filtrados por estado, responsable, etiqueta o fecha.",

    quote: "«La transcripción definitiva es la fuente de verdad; el audio es su origen.»",
    privateLabel: "Tuyo",
    privateTitle: "Funciona en tus máquinas.",
    privateText:
      "Tu audio, tus transcripciones y tus notas nunca salen de tus servidores. Lo único que sale de la aplicación es el texto que se envía al servidor del modelo de lenguaje que <em>tú</em> eliges: Ollama o cualquier servidor compatible con OpenAI, como llama.cpp, llama-swap o vLLM.",

    openLabel: "Código abierto",
    openTitle: "Software libre. Léelo, ejecútalo, cámbialo.",
    openText:
      "AdVera es de código abierto bajo la licencia GNU AGPL-3.0. Puedes leer cada línea, ejecutarlo para lo que quieras, modificarlo y compartirlo, sin cuenta, sin telemetría y sin ataduras. Si ofreces una versión modificada como servicio, compartes tus cambios con la misma licencia, así que las mejoras siguen al alcance de todos.",
    openButton: "Ver el código en GitHub",
    openLicense: "Leer la licencia →",

    howLabel: "Cómo funciona",
    howTitle: "De una conversación a conocimiento que puedes comprobar.",
    step1: "Capturar",
    step1Text:
      "Graba desde el navegador o desde el agente de escritorio de Windows, con el micrófono y el sonido del sistema en pistas separadas. O importa un archivo.",
    step2: "Transcribir",
    step2Text: "Whisper convierte el audio en una transcripción definitiva, con el idioma de cada fragmento y quién habla.",
    step3: "Resumir",
    step3Text:
      "Tu modelo de lenguaje extrae el resumen, las decisiones, acciones, dudas, riesgos y conceptos, cada uno con sus citas.",
    step4: "Recordar",
    step4Text:
      "El Brain lo indexa con el resto de tus reuniones: búsqueda, grafo, líneas de tiempo y todas las decisiones en un solo sitio.",

    installLabel: "Instalar",
    installTitle: "En marcha con un solo comando.",
    installText:
      "AdVera funciona con Docker Compose: PostgreSQL con pgvector, Redis, la API, tres workers y la aplicación web. La primera vez, un breve asistente te pide el idioma y tu servidor del modelo. Podrás cambiarlo todo más adelante en Ajustes.",
    installStep1: "1. Descarga el código",
    installStep2: "2. Arráncalo (CPU)",
    installGpu: "O con una GPU NVIDIA",
    installOpen: "Después abre <code>http://localhost:5173</code>.",

    needTitle: "Qué necesitas",
    needSoftware: "Software",
    needSoftwareText: "Docker con Compose v2. Para usar GPU, el NVIDIA Container Toolkit.",
    needModel: "Un servidor del modelo",
    needModelText:
      "Ollama o un servidor compatible con OpenAI, accesible desde los contenedores, con salida JSON por esquema y una ventana de contexto grande.",
    needTranscription: "Transcripción",
    needTranscriptionText:
      "Funciona con CPU. Una GPU NVIDIA la hace mucho más rápida y precisa; en nuestra máquina de pruebas los workers usan unos 5 GB de VRAM.",
    needDisk: "Disco",
    needDiskText: "Unos 11 GB para los modelos, más tu audio.",
    needNetwork: "Red",
    needNetworkText: "Internet en el primer arranque para descargar los modelos. Después funciona en tu red local.",
    needNote:
      "AdVera todavía no tiene autenticación: está pensado para un solo usuario en una red local. No lo expongas a internet.",

    closingButton: "Consigue AdVera en GitHub",
    footer: "Código abierto (AGPL-3.0). Autoalojado. Tus reuniones siguen siendo tuyas.",
    credit: "Modelo del cerebro:",
    creditBy: "de",
    copy: "Copiar",
    copied: "Copiado",
  };
  var EN = { copy: "Copy", copied: "Copied" };
  var LANGUAGES = ["en", "es"];
  var KEY = "advera.landing.lang";

  function stored() {
    try {
      return window.localStorage.getItem(KEY);
    } catch (error) {
      return null; // storage blocked: the default applies
    }
  }

  function initial() {
    var asked = new URLSearchParams(window.location.search).get("lang");
    if (LANGUAGES.indexOf(asked) >= 0) return asked;
    var saved = stored();
    return LANGUAGES.indexOf(saved) >= 0 ? saved : "en";
  }

  var english = {}; // the English of each element, read from the HTML the first time
  var current = initial();
  var root = document.documentElement;
  root.lang = current;
  // Spanish is applied once the page is parsed: hide it until then so English never flashes.
  if (current !== "en") root.classList.add("i18n-pending");

  function apply(lang) {
    current = lang;
    root.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach(function (element) {
      var key = element.getAttribute("data-i18n");
      if (!(key in english)) english[key] = element.innerHTML;
      element.innerHTML = lang === "es" && ES[key] ? ES[key] : english[key];
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (element) {
      var key = "aria:" + element.getAttribute("data-i18n-aria");
      if (!(key in english)) english[key] = element.getAttribute("aria-label");
      var es = ES[element.getAttribute("data-i18n-aria")];
      element.setAttribute("aria-label", lang === "es" && es ? es : english[key]);
    });
    if (!("title" in english)) english.title = document.title;
    document.title = lang === "es" ? ES.pageTitle : english.title;
    var description = document.querySelector('meta[name="description"]');
    if (description) {
      if (!("description" in english)) english.description = description.getAttribute("content");
      description.setAttribute("content", lang === "es" ? ES.pageDescription : english.description);
    }
    document.querySelectorAll("[data-lang]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-lang") === lang));
    });
    root.classList.remove("i18n-pending");
    document.dispatchEvent(new CustomEvent("languagechange"));
  }

  window.AdVeraI18n = {
    t: function (key) {
      return (current === "es" ? ES : EN)[key] || EN[key] || key;
    },
    lang: function () {
      return current;
    },
  };

  document.addEventListener("DOMContentLoaded", function () {
    apply(current);
    document.querySelectorAll("[data-lang]").forEach(function (button) {
      button.addEventListener("click", function () {
        var lang = button.getAttribute("data-lang");
        try {
          window.localStorage.setItem(KEY, lang);
        } catch (error) {
          // not remembered, but the page still changes
        }
        apply(lang);
      });
    });
  });
})();
