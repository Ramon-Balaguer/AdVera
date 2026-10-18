// The "In action" tour: tabs that switch the screenshot and its caption. It moves on by itself
// every few seconds while it is on screen, until someone picks a tab (never with reduced motion).
(function () {
  var DELAY = 6000;

  document.addEventListener("DOMContentLoaded", function () {
    var tour = document.getElementById("tour");
    if (!tour) return;
    var tabs = Array.prototype.slice.call(tour.querySelectorAll('[role="tab"]'));
    var panel = document.getElementById("tour-screen");
    var shots = tour.querySelectorAll(".screen-shots img");
    var captions = tour.querySelectorAll(".screen-caption-text");
    var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var timer = null;
    var visible = false;

    function select(index, focus) {
      var tab = tabs[index];
      var shot = tab.getAttribute("data-shot");
      tabs.forEach(function (other) {
        var on = other === tab;
        other.setAttribute("aria-selected", String(on));
        other.tabIndex = on ? 0 : -1;
      });
      panel.setAttribute("aria-labelledby", tab.id);
      shots.forEach(function (img) {
        var on = img.getAttribute("data-shot") === shot;
        if (on) img.loading = "eager";
        img.classList.toggle("is-active", on);
      });
      captions.forEach(function (caption) {
        caption.hidden = caption.getAttribute("data-shot") !== shot;
      });
      if (focus) tab.focus();
    }

    function current() {
      return tabs.findIndex(function (tab) {
        return tab.getAttribute("aria-selected") === "true";
      });
    }

    function stop() {
      window.clearInterval(timer);
      timer = null;
    }

    function play() {
      if (still || timer || !visible) return;
      timer = window.setInterval(function () {
        select((current() + 1) % tabs.length, false);
      }, DELAY);
    }

    tabs.forEach(function (tab, index) {
      tab.addEventListener("click", function () {
        still = true; // someone is looking: leave the choice to them
        stop();
        select(index, false);
      });
      tab.addEventListener("keydown", function (event) {
        var next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 }[event.key];
        if (next === undefined) return;
        event.preventDefault();
        still = true;
        stop();
        select((next + tabs.length) % tabs.length, true);
      });
    });

    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        visible = entries[0].isIntersecting;
        if (visible) play();
        else stop();
      }, { threshold: 0.4 }).observe(panel);
    }
  });
})();
