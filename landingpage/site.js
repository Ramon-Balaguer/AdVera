// Small enhancements; the page works without them.
(function () {
  // The repository address lives here only: change it once and every link follows.
  var REPO_URL = "https://github.com/your-org/advera";
  document.querySelectorAll("[data-repo]").forEach(function (link) {
    link.setAttribute("href", REPO_URL);
  });
  document.querySelectorAll("pre code").forEach(function (code) {
    code.textContent = code.textContent.replace("https://github.com/your-org/advera", REPO_URL);
  });

  // A copy button on every command.
  document.querySelectorAll("[data-copy]").forEach(function (block) {
    var code = block.querySelector("code");
    if (!code || !navigator.clipboard) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    button.addEventListener("click", function () {
      navigator.clipboard.writeText(code.textContent).then(function () {
        button.textContent = "Copied";
        button.classList.add("done");
        setTimeout(function () {
          button.textContent = "Copy";
          button.classList.remove("done");
        }, 1600);
      });
    });
    block.appendChild(button);
  });
})();
