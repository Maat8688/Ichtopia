// Statistieken: tooltips bij de grafieken, en het blok 'Nu bezig' verversen.
(function () {
  "use strict";

  // ---- Tooltip: bij aanwijzen met de muis en bij tabben met het toetsenbord.
  // Alle tekst gaat via textContent: namen van plekken en kaarten komen uit
  // de database en horen nooit als HTML gelezen te worden.
  var tip = document.getElementById("tip");

  function vul(el) {
    tip.textContent = "";
    var regels = (el.getAttribute("data-tip-regels") || "").split("|");
    regels.forEach(function (regel) {
      if (!regel) return;
      var r = document.createElement("span");
      r.className = "tip-regel";
      r.textContent = regel;
      tip.appendChild(r);
    });
    var titel = document.createElement("span");
    titel.className = "tip-titel";
    titel.textContent = el.getAttribute("data-tip-titel") || "";
    tip.appendChild(titel);
    tip.hidden = false;
  }

  function plaats(x, y) {
    var b = tip.offsetWidth, h = tip.offsetHeight;
    var links = Math.min(window.innerWidth - b - 8, x + 14);
    var boven = y - h - 12 < 8 ? y + 16 : y - h - 12;
    tip.style.left = Math.max(8, links) + "px";
    tip.style.top = boven + "px";
  }

  function verberg() {
    tip.hidden = true;
  }

  document.querySelectorAll("[data-tip-titel]").forEach(function (el) {
    el.addEventListener("pointermove", function (e) {
      vul(el);
      plaats(e.clientX, e.clientY);
    });
    el.addEventListener("pointerleave", verberg);
    el.addEventListener("focus", function () {
      vul(el);
      var r = el.getBoundingClientRect();
      plaats(r.left + r.width / 2, r.top);
    });
    el.addEventListener("blur", verberg);
  });
  window.addEventListener("scroll", verberg, { passive: true });

  // ---- 'Nu bezig' elke 15 seconden bijwerken, zonder de hele pagina te laden.
  var nu = document.getElementById("nu");
  if (!nu) return;
  function ververs() {
    fetch(nu.getAttribute("data-bron"), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        document.getElementById("nuOefenen").textContent = d.oefenen.active;
        document.getElementById("nuQuiz").textContent = d.inQuiz;
        var n = d.quizzen.length;
        document.getElementById("nuQuizBij").textContent = n + (n === 1 ? " quiz" : " quizzen") + " bezig";
        var kaarten = Object.keys(d.oefenen.perMap).map(function (k) {
          return k + " (" + d.oefenen.perMap[k] + ")";
        });
        document.getElementById("nuKaarten").textContent = kaarten.length ? kaarten.join(" · ") : "niemand";
      })
      .catch(function () {});
  }
  setInterval(ververs, 15000);
})();
