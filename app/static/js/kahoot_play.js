/* Speler (leerling) voor de klassikale quiz. */
(function () {
  let stored = null;
  try {
    stored = JSON.parse(localStorage.getItem("kahootPlayer-" + KAHOOT.pin));
  } catch (e) {
    stored = null;
  }
  if (!stored || !stored.playerId) {
    window.location.href = "/join?pin=" + KAHOOT.pin;
    return;
  }

  const socket = io();

  const sections = {
    waiting: document.getElementById("waiting"),
    question: document.getElementById("question"),
    answered: document.getElementById("answered"),
    result: document.getElementById("result"),
    finished: document.getElementById("finished"),
  };

  const els = {
    playerName: document.getElementById("playerName"),
    playerScore: document.getElementById("playerScore"),
    timer: document.getElementById("timer"),
    timerValue: document.getElementById("timerValue"),
    prompt: document.getElementById("prompt"),
    questionCounter: document.getElementById("questionCounter"),
    options: document.getElementById("options"),
    result: document.getElementById("result"),
    resultTitle: document.getElementById("resultTitle"),
    resultPoints: document.getElementById("resultPoints"),
    resultCorrect: document.getElementById("resultCorrect"),
    resultScore: document.getElementById("resultScore"),
    resultRank: document.getElementById("resultRank"),
    finalScore: document.getElementById("finalScore"),
    finalRank: document.getElementById("finalRank"),
    finalLeaderboard: document.getElementById("finalLeaderboard"),
    error: document.getElementById("error"),
  };

  let timerInterval = null;
  let currentIndex = -1;
  let hasAnswered = false;

  els.playerName.textContent = stored.name;

  function show(name) {
    Object.keys(sections).forEach((key) => {
      sections[key].classList.toggle("hidden", key !== name);
    });
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.classList.remove("hidden");
  }

  function setScore(score) {
    els.playerScore.textContent = score + " punten";
  }

  function stopTimer() {
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = null;
  }

  function startTimer(seconds, remaining) {
    stopTimer();
    const end = Date.now() + remaining * 1000;
    function tick() {
      const left = Math.max(0, (end - Date.now()) / 1000);
      els.timerValue.textContent = Math.ceil(left);
      els.timer.style.setProperty("--progress", (left / seconds) * 100 + "%");
      els.timer.classList.toggle("urgent", left <= 5);
      if (left <= 0) stopTimer();
    }
    tick();
    timerInterval = setInterval(tick, 100);
  }

  // ------------------------------------------------------------------
  // Antwoorden
  // ------------------------------------------------------------------
  function sendAnswer(answer, hashed) {
    if (hasAnswered) return;
    hasAnswered = true;
    socket.emit("kahootAnswer", {
      pin: KAHOOT.pin,
      playerId: stored.playerId,
      answer: answer,
      hashed: hashed,
    });
    show("answered");
  }

  function clearMapHighlight() {
    document.querySelectorAll("#questions > g").forEach((g) => {
      g.classList.remove("active");
      g.setAttribute("state", "Normal");
    });
  }

  // Klik-modus: elk gebied op de kaart is een antwoord.
  document.querySelectorAll("#questions > g").forEach((g) => {
    g.addEventListener("click", () => {
      if (sections.question.classList.contains("hidden")) return;
      g.classList.add("active");
      sendAnswer(g.getAttribute("id"), true);
    });
    // Een <g> is geen knop, dus Enter en spatie moeten we zelf afvangen.
    g.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        g.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      }
    });
  });

  // ------------------------------------------------------------------
  // Vraag
  // ------------------------------------------------------------------
  function renderQuestion(q, alreadyAnswered) {
    currentIndex = q.index;
    hasAnswered = !!alreadyAnswered;
    els.questionCounter.textContent = q.number + " / " + q.total;
    els.prompt.textContent = q.prompt;

    if (q.mode === 1 && els.options) {
      els.options.innerHTML = "";
      q.options.forEach((option, i) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "k-option";
        button.dataset.color = i % 4;
        button.innerHTML = '<span class="k-shape"></span><span class="k-text"></span>';
        button.querySelector(".k-text").textContent = option;
        button.addEventListener("click", () => sendAnswer(option, false));
        els.options.appendChild(button);
      });
    } else {
      clearMapHighlight();
    }

    startTimer(q.seconds, q.remaining !== undefined ? q.remaining : q.seconds);
    show(hasAnswered ? "answered" : "question");
  }

  // ------------------------------------------------------------------
  // Resultaat
  // ------------------------------------------------------------------
  function renderResult(r) {
    stopTimer();
    setScore(r.score);
    els.result.classList.remove("good", "bad", "none");
    if (!r.answered) {
      els.result.classList.add("none");
      els.resultTitle.textContent = "Te laat!";
      els.resultPoints.textContent = "+0";
    } else if (r.correct) {
      els.result.classList.add("good");
      els.resultTitle.textContent = "Goed!";
      els.resultPoints.textContent = "+" + r.points;
    } else {
      els.result.classList.add("bad");
      els.resultTitle.textContent = "Helaas...";
      els.resultPoints.textContent = "+0";
    }
    els.resultCorrect.textContent = r.correctAnswer ? "Het goede antwoord was: " + r.correctAnswer : "";
    els.resultScore.textContent = r.score;
    els.resultRank.textContent = "Plaats " + r.rank + " van " + r.players;
    show("result");
  }

  function renderFinished(data) {
    stopTimer();
    setScore(data.score);
    els.finalScore.textContent = data.score + " punten";
    els.finalRank.textContent = "Plaats " + data.rank + " van " + data.players;
    els.finalLeaderboard.innerHTML = "";
    (data.leaderboard || []).slice(0, 10).forEach((entry) => {
      const li = document.createElement("li");
      if (entry.id === stored.playerId) li.classList.add("me");
      li.innerHTML = '<span class="k-rank"></span><span class="k-name"></span><span></span><span class="k-score"></span>';
      li.querySelector(".k-rank").textContent = entry.rank;
      li.querySelector(".k-name").textContent = entry.name;
      li.querySelector(".k-score").textContent = entry.score;
      els.finalLeaderboard.appendChild(li);
    });
    show("finished");
  }

  // ------------------------------------------------------------------
  // Socket-events
  // ------------------------------------------------------------------
  socket.on("connect", () => {
    socket.emit("kahootRejoin", { pin: KAHOOT.pin, playerId: stored.playerId });
  });

  socket.on("kahootState", (state) => {
    setScore(state.score);
    if (state.state === "lobby") {
      show("waiting");
    } else if (state.state === "question") {
      renderQuestion(state.question, state.answered);
    } else if (state.state === "reveal") {
      renderResult(state.result);
    } else if (state.state === "finished") {
      renderFinished(Object.assign({ leaderboard: state.leaderboard }, state.result));
    }
  });

  socket.on("kahootQuestion", (q) => renderQuestion(q, false));
  socket.on("kahootResult", renderResult);
  socket.on("kahootFinished", renderFinished);

  socket.on("kahootAnswerRejected", () => {
    // Bijvoorbeeld te laat: laat de wachtpagina staan, de uitslag komt zo.
    hasAnswered = true;
    show("answered");
  });

  socket.on("kahootKicked", (data) => {
    try {
      localStorage.removeItem("kahootPlayer-" + KAHOOT.pin);
    } catch (e) {}
    window.location.href = "/join?pin=" + KAHOOT.pin + "&kicked=1";
  });

  socket.on("kahootError", (data) => {
    showError(data.message || "Er ging iets mis.");
    if (data.fatal) {
      try {
        localStorage.removeItem("kahootPlayer-" + KAHOOT.pin);
      } catch (e) {}
      setTimeout(() => (window.location.href = "/join"), 3000);
    }
  });
})();
