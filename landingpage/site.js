// Small enhancements; the page works without them.
(function () {
  // The repository address lives here only: change it once and every link follows.
  var REPO_URL = "https://github.com/Ramon-Balaguer/AdVera";
  document.querySelectorAll("[data-repo]").forEach(function (link) {
    // A link may point inside the repository (data-repo-path="blob/main/LICENSE").
    var path = link.getAttribute("data-repo-path");
    link.setAttribute("href", path ? REPO_URL + "/" + path : REPO_URL);
  });
  document.querySelectorAll("pre code").forEach(function (code) {
    code.textContent = code.textContent.replace("https://github.com/Ramon-Balaguer/AdVera", REPO_URL);
  });

  // A copy button on every command.
  document.querySelectorAll("[data-copy]").forEach(function (block) {
    var code = block.querySelector("code");
    if (!code || !navigator.clipboard) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    var t = function (key) {
      return window.AdVeraI18n ? window.AdVeraI18n.t(key) : key === "copy" ? "Copy" : "Copied";
    };
    button.textContent = t("copy");
    document.addEventListener("languagechange", function () {
      if (!button.classList.contains("done")) button.textContent = t("copy");
    });
    button.addEventListener("click", function () {
      navigator.clipboard.writeText(code.textContent).then(function () {
        button.textContent = t("copied");
        button.classList.add("done");
        setTimeout(function () {
          button.textContent = t("copy");
          button.classList.remove("done");
        }, 1600);
      });
    });
    block.appendChild(button);
  });
})();
