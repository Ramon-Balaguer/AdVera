// The background of the whole page: small outlined triangles of colour drifting slowly upwards
// behind the content, with a little parallax that follows the pointer. A fixed canvas the size
// of the window; with "reduced motion" it is drawn once and stays still.
(function () {
  var canvas = document.getElementById("ambient");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var COLORS = ["#8052ff", "#ffb829", "#15846e", "#ff4fa3", "#3d8bff", "#a56bff", "#2fd6a5", "#ffd166"];
  var ALPHA = 0.3;

  var width = 0;
  var height = 0;
  var points = [];
  var shift = { x: 0, y: 0, tx: 0, ty: 0 };

  function seed() {
    var ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    // About one triangle per 15,000 square pixels, between 40 and 130.
    var count = Math.round(Math.min(130, Math.max(40, (width * height) / 15000)));
    points = [];
    for (var i = 0; i < count; i++) {
      points.push({
        x: Math.random() * width,
        y: Math.random() * height,
        size: 1.4 + Math.random() * 2.6,
        color: i % COLORS.length,
        vx: (Math.random() - 0.5) * 0.14,
        vy: -0.05 - Math.random() * 0.16,
        phase: Math.random() * Math.PI * 2,
      });
    }
  }

  function triangle(path, x, y, s) {
    path.moveTo(x, y - s);
    path.lineTo(x + s * 0.866, y + s * 0.5);
    path.lineTo(x - s * 0.866, y + s * 0.5);
    path.closePath();
  }

  function draw(t) {
    shift.x += (shift.tx - shift.x) * 0.045;
    shift.y += (shift.ty - shift.y) * 0.045;
    ctx.clearRect(0, 0, width, height);
    var paths = COLORS.map(function () {
      return new Path2D();
    });
    for (var i = 0; i < points.length; i++) {
      var p = points[i];
      if (!still) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.y < -12) {
          p.y = height + 10;
          p.x = Math.random() * width;
        }
        if (p.x < -12) p.x = width + 10;
        if (p.x > width + 12) p.x = -10;
      }
      var twinkle = 1 + Math.sin(t * 0.0009 + p.phase) * 0.32;
      triangle(paths[p.color], p.x + shift.x, p.y + shift.y, p.size * twinkle);
    }
    ctx.globalAlpha = ALPHA;
    ctx.lineWidth = 1;
    for (var c = 0; c < paths.length; c++) {
      ctx.strokeStyle = COLORS[c];
      ctx.stroke(paths[c]);
    }
    ctx.globalAlpha = 1;
  }

  function frame(time) {
    draw(time);
    requestAnimationFrame(frame);
  }

  var resizing;
  window.addEventListener("resize", function () {
    clearTimeout(resizing);
    resizing = setTimeout(function () {
      seed();
      if (still) draw(0);
    }, 180);
  });
  window.addEventListener(
    "pointermove",
    function (event) {
      shift.tx = (event.clientX / window.innerWidth - 0.5) * 16;
      shift.ty = (event.clientY / window.innerHeight - 0.5) * 12;
    },
    { passive: true },
  );

  seed();
  if (still) draw(0);
  else requestAnimationFrame(frame);
})();
