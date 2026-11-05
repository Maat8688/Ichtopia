/* Haalt het laadscherm weg zodra de pagina klaar is.
   Het scherm mag nooit blijven hangen, dus er zit ook een noodrem op. */
(function () {
  var screen = document.getElementById("loadingScreen");
  if (!screen) return;

  var hidden = false;

  function hide() {
    if (hidden) return;
    hidden = true;
    screen.classList.add("done");
    // Pas na de fade echt weghalen, anders vangt het overlay nog klikken op.
    setTimeout(function () {
      screen.hidden = true;
    }, 300);
  }

  if (document.readyState === "complete") {
    hide();
  } else {
    window.addEventListener("load", hide);
  }

  // Laadt er iets niet (trage afbeelding, CDN onbereikbaar)? Dan toch door.
  setTimeout(hide, 8000);
})();
