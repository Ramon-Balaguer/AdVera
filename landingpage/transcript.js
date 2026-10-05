// The example transcript follows a play head: the line being "heard" is lit, one after another.
(function () {
  var lines = document.querySelectorAll(".transcript .tline");
  var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!lines.length || still) return;
  var current = 3;
  setInterval(function () {
    lines[current].classList.remove("is-hot");
    current = (current + 1) % lines.length;
    lines[current].classList.add("is-hot");
  }, 2600);
})();
