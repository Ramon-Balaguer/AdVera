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
  var BASE_TURN = -0.6; // radians around the vertical axis: brings the front towards the viewer
  var BASE_TILT = -0.22; // and a little from above
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

  // The shape is drawn once, as a picture, on a hidden canvas: the outline of a brain seen from
  // the left (front to the right, y down) with its lobes and the brainstem, then the main fissures and many smaller
  // folds are cut out of it. Particles are kept only where the picture is filled, and more of them
  // along its edges, so the outline and the folds can be read.
  var MASK = 420; // the picture is MASK x MASK pixels for the square [-1, 1] x [-1, 1]

  function toMask(v) {
    return ((v + 1) / 2) * MASK;
  }

  function outline() {
    var p = new Path2D();
    // Cerebrum: frontal pole, over the top, down the back to the occipital pole, along the
    // underside of the temporal lobe to its pole, into the lateral fissure and back to the front.
    var pts = [
      [0.93, 0.16],
      [1.02, -0.14, 0.94, -0.5, 0.64, -0.69],
      [0.36, -0.86, -0.04, -0.9, -0.36, -0.8],
      [-0.7, -0.68, -0.95, -0.42, -0.97, -0.1],
      [-0.99, 0.1, -0.92, 0.27, -0.76, 0.3],
      [-0.45, 0.36, 0.05, 0.55, 0.38, 0.5],
      [0.58, 0.47, 0.64, 0.33, 0.52, 0.24],
      [0.44, 0.2, 0.42, 0.17, 0.48, 0.15],
      [0.62, 0.13, 0.82, 0.22, 0.93, 0.16],
    ];
    p.moveTo(toMask(pts[0][0]), toMask(pts[0][1]));
    for (var i = 1; i < pts.length; i++) {
      var c = pts[i];
      p.bezierCurveTo(toMask(c[0]), toMask(c[1]), toMask(c[2]), toMask(c[3]), toMask(c[4]), toMask(c[5]));
    }
    p.closePath();
    // Brainstem, under the back half of the brain, going down and slightly forward.
    p.moveTo(toMask(-0.6), toMask(0.28));
    p.bezierCurveTo(toMask(-0.56), toMask(0.52), toMask(-0.52), toMask(0.76), toMask(-0.5), toMask(0.96));
    p.lineTo(toMask(-0.35), toMask(0.96));
    p.bezierCurveTo(toMask(-0.36), toMask(0.76), toMask(-0.38), toMask(0.54), toMask(-0.4), toMask(0.34));
    p.closePath();
    return p;
  }

  function stroke(g, points, widthUnits) {
    g.lineWidth = (widthUnits * MASK) / 2;
    g.beginPath();
    g.moveTo(toMask(points[0][0]), toMask(points[0][1]));
    for (var i = 1; i < points.length; i++) g.lineTo(toMask(points[i][0]), toMask(points[i][1]));
    g.stroke();
  }

  // A meandering fold: a short walk whose direction keeps turning, like a sulcus.
  function sulcus(g, x, y, steps, heading) {
    var points = [[x, y]];
    for (var i = 0; i < steps; i++) {
      heading += (random() - 0.5) * 0.9;
      x += Math.cos(heading) * 0.035;
      y += Math.sin(heading) * 0.035;
      points.push([x, y]);
    }
    stroke(g, points, 0.022);
  }

  function buildMask() {
    var mask = document.createElement("canvas");
    mask.width = MASK;
    mask.height = MASK;
    var g = mask.getContext("2d");
    var shape = outline();
    g.fillStyle = "#fff";
    g.fill(shape);
    g.globalCompositeOperation = "destination-out";
    g.strokeStyle = "#000";
    g.lineCap = "round";
    g.lineJoin = "round";
    // The lateral (Sylvian) fissure, between the temporal lobe and the rest.
    stroke(g, [[0.46, 0.16], [0.3, 0.12], [0.1, 0.06], [-0.1, -0.01], [-0.3, -0.08]], 0.04);
    // The central sulcus, from the top down towards the lateral fissure.
    stroke(g, [[0.12, -0.88], [0.06, -0.6], [0.0, -0.36], [-0.04, -0.14], [-0.02, 0.02]], 0.032);
    // The parieto-occipital sulcus.
    stroke(g, [[-0.62, -0.7], [-0.7, -0.5], [-0.74, -0.32]], 0.03);
    // Many small folds, only inside the cerebrum.
    g.save();
    g.clip(shape);
    for (var i = 0; i < 46; i++) {
      var x = random() * 1.8 - 0.9;
      var y = random() * 1.3 - 0.85;
      sulcus(g, x, y, 4 + Math.floor(random() * 7), random() * Math.PI * 2);
    }
    g.restore();
    return g.getImageData(0, 0, MASK, MASK).data;
  }

  function filled(data, x, y) {
    var px = Math.floor(toMask(x));
    var py = Math.floor(toMask(y));
    if (px < 0 || py < 0 || px >= MASK || py >= MASK) return false;
    return data[(py * MASK + px) * 4 + 3] > 128;
  }

  // How far a point is from the edge of the picture, in mask units (up to `limit`).
  function edgeDistance(data, x, y, limit) {
    var step = 2 / MASK;
    for (var r = 1; r <= limit; r++) {
      for (var k = 0; k < 8; k++) {
        var a = (k * Math.PI) / 4;
        if (!filled(data, x + Math.cos(a) * r * step, y + Math.sin(a) * r * step)) return r;
      }
    }
    return limit;
  }

  var particles = [];

  // The 3D model's points (brain-points.js, from "Brain Areas" by Versal, CC BY 4.0): when they
  // are there, the brain is the model's real surface instead of the drawn outline below.
  function buildFromModel(count) {
    var source = window.BRAIN_POINTS;
    var total = source.length / 4;
    var every = Math.max(1, Math.round(total / count));
    particles = [];
    for (var i = 0; i < total; i += every) {
      particles.push({
        x: source[i * 4],
        y: source[i * 4 + 1],
        z: source[i * 4 + 2],
        part: source[i * 4 + 3],
        size: 1.2 + random() * 2.4,
        spin: random() * Math.PI * 2,
        spinSpeed: (random() - 0.5) * 0.0012,
        color: pickColor(),
        phase: random() * Math.PI * 2,
      });
    }
  }

  function build(count) {
    if (window.BRAIN_POINTS && window.BRAIN_POINTS.length) {
      buildFromModel(count);
      return;
    }
    var data = buildMask();
    particles = [];
    var guard = 0;
    var LIMIT = 40;
    while (particles.length < count && guard < count * 60) {
      guard++;
      var x = random() * 2 - 1;
      var y = random() * 2 - 1;
      if (!filled(data, x, y)) continue;
      var d = edgeDistance(data, x, y, LIMIT);
      // Edges (outline and folds) keep every point; the inside keeps fewer, so they stand out.
      if (d > 3 && random() < 0.55) continue;
      // The volume: thick in the middle of a lobe, thin at its edge, more points near the surface.
      var half = 0.5 * Math.sqrt(Math.min(1, d / LIMIT));
      var side = random() < 0.5 ? -1 : 1;
      var z = side * half * (0.6 + 0.4 * Math.sqrt(random()));
      particles.push({
        x: x,
        y: y - 0.02,
        z: z,
        size: 1.3 + random() * 2.6,
        spin: random() * Math.PI * 2,
        spinSpeed: (random() - 0.5) * 0.0012,
        color: pickColor(),
        phase: random() * Math.PI * 2,
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
    // The resting view is three quarters, a little from the front; it sways around it.
    var turn = BASE_TURN + Math.sin(t * 0.00012) * 0.3 + pointer.x * 0.3;
    var tilt = BASE_TILT + pointer.y * 0.12;
    var cosY = Math.cos(turn);
    var sinY = Math.sin(turn);
    var cosX = Math.cos(tilt);
    var sinX = Math.sin(tilt);

    var i;
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

  build(window.innerWidth < 700 ? 1900 : 3400);
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
