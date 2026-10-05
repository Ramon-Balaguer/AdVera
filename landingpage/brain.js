// The brain: thousands of small outlined triangles in a brain-shaped volume, slowly turning,
// with sparks of amber travelling between them (a citation connecting two moments). Plain
// canvas, no libraries. It stops when it is off screen and stays still for reduced motion.
(function () {
  var canvas = document.getElementById("brain-canvas");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var COLORS = ["#8052ff", "#a78bfa", "#ffb829", "#15846e", "#2dd4bf", "#ff5fd2", "#4f8bff"];
  var WEIGHTS = [0.3, 0.14, 0.15, 0.1, 0.11, 0.1, 0.1];
  var LEVELS = 3; // depth bands, so each colour is stroked in three passes, not once per triangle

  // A deterministic random, so the brain has the same shape on every visit.
  var seed = 7;
  function random() {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  }

  function pickColor() {
    var r = random();
    for (var i = 0; i < WEIGHTS.length; i++) {
      r -= WEIGHTS[i];
      if (r <= 0) return i;
    }
    return 0;
  }

  // Side view, front to the right, y down. Inside the brain when one of these regions holds.
  function inEllipse(x, y, cx, cy, rx, ry) {
    var dx = (x - cx) / rx;
    var dy = (y - cy) / ry;
    return dx * dx + dy * dy;
  }

  function shape(x, y) {
    var angle = Math.atan2(y + 0.08, x);
    var wobble = 0.035 * Math.sin(angle * 9) + 0.02 * Math.sin(angle * 17 + 1);
    var cerebrum = inEllipse(x, y, 0, -0.08, 0.92, y < -0.08 ? 0.64 : 0.46);
    if (cerebrum <= 1 + wobble) return Math.min(1, cerebrum);
    var temporal = inEllipse(x, y, 0.18, 0.26, 0.5, 0.2);
    if (temporal <= 1) return temporal;
    var cerebellum = inEllipse(x, y, -0.56, 0.4, 0.3, 0.17);
    if (cerebellum <= 1 + 0.08 * Math.sin(x * 40)) return cerebellum;
    var stem = inEllipse(x, y, -0.25, 0.6, 0.085, 0.24);
    if (stem <= 1) return stem;
    return -1;
  }

  // The folds: points close to these curves are thinned out, which draws the gyri.
  function fold(x, y) {
    var g = Math.sin(9 * x + 3 * Math.sin(5 * y)) * Math.sin(8 * y + 2 * Math.sin(4 * x));
    var central = Math.abs(x - (0.05 - 0.22 * (y + 0.68))) < 0.025 && y < 0.1;
    var lateral = Math.abs(y - (0.1 - 0.2 * (0.45 - x))) < 0.022 && x > -0.3 && x < 0.5;
    return Math.abs(g) < 0.1 || central || lateral;
  }

  var particles = [];
  var ambient = [];

  function build(count) {
    particles = [];
    var guard = 0;
    while (particles.length < count && guard < count * 40) {
      guard++;
      var x = random() * 2 - 1;
      var y = random() * 1.7 - 0.85;
      var depth = shape(x, y);
      if (depth < 0) continue;
      if (fold(x, y) && random() < 0.85) continue;
      // Thicker in the middle of the shape, thinner at its edge; more points near the surface.
      var half = 0.55 * Math.sqrt(Math.max(0.02, 1 - depth));
      var side = random() < 0.5 ? -1 : 1;
      var z = side * half * (0.55 + 0.45 * Math.sqrt(random()));
      particles.push({
        x: x,
        y: y,
        z: z,
        size: 1.6 + random() * 3.2,
        spin: random() * Math.PI * 2,
        spinSpeed: (random() - 0.5) * 0.0012,
        color: pickColor(),
        phase: random() * Math.PI * 2,
      });
    }
    ambient = [];
    for (var i = 0; i < 160; i++) {
      ambient.push({
        x: random(),
        y: random(),
        size: 1 + random() * 2.2,
        spin: random() * Math.PI * 2,
        vx: (random() - 0.5) * 0.00002,
        vy: -0.000006 - random() * 0.00002,
        color: pickColor(),
        alpha: 0.12 + random() * 0.3,
      });
    }
  }

  var width = 0;
  var height = 0;
  var ratio = 1;
  var radius = 0;

  function resize() {
    var box = canvas.getBoundingClientRect();
    ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, Math.round(box.width));
    height = Math.max(1, Math.round(box.height));
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    radius = Math.min(width, height) * 0.46;
    if (still) draw(0);
  }

  var pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  window.addEventListener(
    "pointermove",
    function (event) {
      pointer.tx = (event.clientX / window.innerWidth) * 2 - 1;
      pointer.ty = (event.clientY / window.innerHeight) * 2 - 1;
    },
    { passive: true },
  );

  function triangle(path, x, y, size, spin) {
    for (var k = 0; k < 3; k++) {
      var a = spin + (k * Math.PI * 2) / 3;
      var px = x + Math.cos(a) * size;
      var py = y + Math.sin(a) * size;
      if (k === 0) path.moveTo(px, py);
      else path.lineTo(px, py);
    }
    path.closePath();
  }

  // Sparks: an amber line that grows from one particle to a near one and fades.
  var sparks = [];
  var lastSpark = 0;
  var projected = [];

  function addSpark(time) {
    if (projected.length < 2) return;
    var from = projected[Math.floor(random() * projected.length)];
    var best = null;
    var bestDistance = Infinity;
    for (var i = 0; i < 24; i++) {
      var other = projected[Math.floor(random() * projected.length)];
      var d = (other.sx - from.sx) * (other.sx - from.sx) + (other.sy - from.sy) * (other.sy - from.sy);
      if (other !== from && d > 400 && d < bestDistance) {
        best = other;
        bestDistance = d;
      }
    }
    if (best) sparks.push({ from: from.p, to: best.p, start: time });
  }

  function project(p, cosY, sinY, cosX, sinX, t) {
    var breathe = 1 + 0.012 * Math.sin(t * 0.0008 + p.phase);
    var x = p.x * breathe;
    var y = p.y * breathe;
    var z = p.z * breathe;
    var x1 = x * cosY - z * sinY;
    var z1 = x * sinY + z * cosY;
    var y1 = y * cosX - z1 * sinX;
    var z2 = y * sinX + z1 * cosX;
    var scale = 2.6 / (2.6 + z2);
    return { sx: width / 2 + x1 * radius * scale, sy: height / 2 + y1 * radius * scale, z: z2, scale: scale };
  }

  function draw(t) {
    ctx.clearRect(0, 0, width, height);
    pointer.x += (pointer.tx - pointer.x) * 0.04;
    pointer.y += (pointer.ty - pointer.y) * 0.04;
    var turn = Math.sin(t * 0.00012) * 0.42 + pointer.x * 0.3;
    var tilt = -0.12 + pointer.y * 0.12;
    var cosY = Math.cos(turn);
    var sinY = Math.sin(turn);
    var cosX = Math.cos(tilt);
    var sinX = Math.sin(tilt);

    // Ambient triangles drifting around the brain.
    var i;
    ctx.lineWidth = 1;
    for (i = 0; i < ambient.length; i++) {
      var a = ambient[i];
      if (!still) {
        a.x = (a.x + a.vx * 16 + 1) % 1;
        a.y = (a.y + a.vy * 16 + 1) % 1;
        a.spin += 0.002;
      }
      ctx.globalAlpha = a.alpha;
      ctx.strokeStyle = COLORS[a.color];
      ctx.beginPath();
      triangle(ctx, a.x * width, a.y * height, a.size, a.spin);
      ctx.stroke();
    }

    // The brain, batched by colour and depth band.
    var paths = [];
    for (i = 0; i < COLORS.length * LEVELS; i++) paths.push(new Path2D());
    projected = [];
    for (i = 0; i < particles.length; i++) {
      var p = particles[i];
      if (!still) p.spin += p.spinSpeed * 16;
      var s = project(p, cosY, sinY, cosX, sinX, t);
      var level = s.z < -0.15 ? 2 : s.z < 0.15 ? 1 : 0;
      triangle(paths[p.color * LEVELS + level], s.sx, s.sy, p.size * s.scale, p.spin);
      if (i % 3 === 0) projected.push({ sx: s.sx, sy: s.sy, p: p });
    }
    ctx.lineWidth = 1.15;
    for (i = 0; i < paths.length; i++) {
      var band = i % LEVELS;
      ctx.globalAlpha = band === 2 ? 0.95 : band === 1 ? 0.7 : 0.38;
      ctx.strokeStyle = COLORS[Math.floor(i / LEVELS)];
      ctx.stroke(paths[i]);
    }

    // Sparks between moments.
    if (!still) {
      if (t - lastSpark > 140 && sparks.length < 7) {
        addSpark(t);
        lastSpark = t;
      }
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = "#ffb829";
      for (i = sparks.length - 1; i >= 0; i--) {
        var spark = sparks[i];
        var age = (t - spark.start) / 1100;
        if (age >= 1) {
          sparks.splice(i, 1);
          continue;
        }
        var from = project(spark.from, cosY, sinY, cosX, sinX, t);
        var to = project(spark.to, cosY, sinY, cosX, sinX, t);
        var grow = Math.min(1, age * 2.2);
        ctx.globalAlpha = Math.sin(age * Math.PI) * 0.9;
        ctx.beginPath();
        ctx.moveTo(from.sx, from.sy);
        ctx.lineTo(from.sx + (to.sx - from.sx) * grow, from.sy + (to.sy - from.sy) * grow);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(to.sx, to.sy, 2.2 * grow, 0, Math.PI * 2);
        ctx.fillStyle = "#ffb829";
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
  }

  var running = false;
  var visible = true;
  function frame(time) {
    if (!visible) {
      running = false;
      return;
    }
    draw(time);
    requestAnimationFrame(frame);
  }

  function start() {
    if (still || running) return;
    running = true;
    requestAnimationFrame(frame);
  }

  build(window.innerWidth < 700 ? 1500 : 2800);
  resize();
  window.addEventListener("resize", resize);

  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting;
      if (visible) start();
    }).observe(canvas);
  }
  if (still) draw(0);
  else start();
})();
