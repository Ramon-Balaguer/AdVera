// The waveform of a recording in progress: bars that breathe, violet for what has already been
// played and faint for what is still ahead, with an amber play head and a running clock.
(function () {
  var canvas = document.getElementById("wave");
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext("2d");
  var clock = document.getElementById("wave-time");
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var BARS = 84;
  var LENGTH = 47 * 60 + 12; // the length shown on the clock, in seconds
  var bars = [];
  var width = 0;
  var height = 0;
  var head = still ? 0.42 : 0;
  var visible = true;

  function build() {
    var ratio = Math.min(window.devicePixelRatio || 1, 2);
    var box = canvas.getBoundingClientRect();
    width = Math.max(1, Math.round(box.width));
    height = Math.max(1, Math.round(box.height));
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    bars = [];
    for (var i = 0; i < BARS; i++) {
      bars.push({
        // Louder in the middle of the meeting, quieter at its ends.
        envelope: Math.pow(Math.sin((Math.PI * i) / BARS), 0.42),
        level: 0.06 + Math.random() * 0.94,
        seed: Math.random() * 100,
        speed: 0.7 + Math.random() * 1.5,
      });
    }
  }

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function draw(t) {
    ctx.clearRect(0, 0, width, height);
    var gap = width / BARS;
    var barWidth = Math.max(1.1, gap * 0.34);
    var middle = height / 2;
    for (var i = 0; i < BARS; i++) {
      var b = bars[i];
      var n = Math.sin(b.seed + t * 0.0011 * b.speed) * 0.5 + Math.sin(b.seed * 2.3 - t * 0.0021) * 0.32;
      var amplitude = b.level * b.envelope * (0.42 + 0.58 * Math.abs(n));
      var barHeight = Math.max(2, amplitude * height * 0.44);
      ctx.fillStyle = i / BARS <= head ? "#8052ff" : "rgba(255, 255, 255, 0.13)";
      ctx.fillRect(i * gap + (gap - barWidth) / 2, middle - barHeight, barWidth, barHeight * 2);
    }
    var x = head * width;
    if (x > 1 && x < width - 1) {
      ctx.fillStyle = "#ffb829";
      ctx.fillRect(x - 0.75, 2, 1.5, height - 4);
    }
    if (clock) {
      var seconds = Math.floor(head * LENGTH);
      clock.textContent = pad(Math.floor(seconds / 60)) + ":" + pad(seconds % 60) + " / 47:12";
    }
  }

  function frame(time) {
    if (visible) {
      head += 0.00055;
      if (head > 1) head -= 1;
      draw(time);
    }
    requestAnimationFrame(frame);
  }

  var resizing;
  window.addEventListener("resize", function () {
    clearTimeout(resizing);
    resizing = setTimeout(function () {
      build();
      if (still) draw(0);
    }, 180);
  });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(
      function (entries) {
        visible = entries[0].isIntersecting;
      },
      { threshold: 0.05 },
    ).observe(canvas);
  }

  build();
  if (still) draw(0);
  else requestAnimationFrame(frame);
})();
