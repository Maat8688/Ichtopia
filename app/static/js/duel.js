/* Speler in een 1-tegen-1 duel. Lijkt op kahoot_play.js, maar met een
   scorebalk voor twee en een uitslag met elo. */
(function () {
  const socket = io();

  const sections = {
    waiting: document.getElementById("waiting"),
    countdown: document.getElementById("countdown"),
    question: document.getElementById("question"),
    answered: document.getElementById("answered"),
    result: document.getElementById("result"),
    finished: document.getElementById("finished"),
  };

  const els = {
    scorebar: document.getElementById("scorebar"),
    meName: document.getElementById("meName"),
    meScore: document.getElementById("meScore"),
    themName: document.getElementById("themName"),
    themScore: document.getElementById("themScore"),
    questionCounter: document.getElementById("questionCounter"),
    waitingText: document.getElementById("waitingText"),
    countdownName: document.getElementById("countdownName"),
    countdownValue: document.getElementById("countdownValue"),
    timer: document.getElementById("timer"),
    timerValue: document.getElementById("timerValue"),
    prompt: document.getElementById("prompt"),
    questionNumber: document.getElementById("questionNumber"),
    options: document.getElementById("options"),
    answeredText: document.getElementById("answeredText"),
    result: document.getElementById("result"),
    resultTitle: document.getElementById("resultTitle"),
    resultPoints: document.getElementById("resultPoints"),
    resultCorrect: document.getElementById("resultCorrect"),
    resultOpponent: document.getElementById("resultOpponent"),
    finalTitle: document.getElementById("finalTitle"),
    finalScore: document.getElementById("finalScore"),
    finalCorrect: document.getElementById("finalCorrect"),
    finalRating: document.getElementById("finalRating"),
    finalXp: document.getElementById("finalXp"),
    error: document.getElementById("error"),
  };

  let timerInterval = null;
  let countdownInterval = null;
  let hasAnswered = false;

  function show(name) {
    Object.keys(sections).forEach(function (key) {
      sections[key].classList.toggle("hidden", key !== name);
    });
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.classList.remove("hidden");
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

  function setScores(me, them) {
    els.scorebar.hidden = false;
    if (me) {
      els.meName.textContent = me.name;
      els.meScore.textContent = me.score;
    }
    if (them) {
      els.themName.textContent = them.name;
      els.themScore.textContent = them.score;
    } else {
      els.themName.textContent = "wacht...";
      els.themScore.textContent = "0";
    }
  }

  // ------------------------------------------------------------------
  // Antwoorden
  // ------------------------------------------------------------------
  function sendAnswer(answer, hashed) {
    if (hasAnswered) return;
    hasAnswered = true;
    socket.emit("duelAnswer", { code: DUEL.code, answer: answer, hashed: hashed });
    show("answered");
  }

  function clearMapHighlight() {
    document.querySelectorAll("#questions > g").forEach(function (g) {
      g.classList.remove("active");
      g.setAttribute("state", "Normal");
    });
  }

  document.querySelectorAll("#questions > g").forEach(function (g) {
    g.addEventListener("click", function () {
      if (sections.question.classList.contains("hidden")) return;
      g.classList.add("active");
      sendAnswer(g.getAttribute("id"), true);
    });
    g.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        g.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      }
    });
  });

  // ------------------------------------------------------------------
  // Schermen
  // ------------------------------------------------------------------
  function renderQuestion(q, alreadyAnswered) {
    hasAnswered = !!alreadyAnswered;
    els.questionNumber.textContent = q.number + " / " + q.total;
    els.questionCounter.textContent = "vraag " + q.number;
    els.prompt.textContent = q.prompt;
    els.answeredText.textContent = "Wachten op je tegenstander...";

    if (q.mode === 1 && els.options) {
      els.options.innerHTML = "";
      q.options.forEach(function (option, i) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "k-option";
        button.dataset.color = i % 4;
        button.innerHTML = '<span class="k-shape"></span><span class="k-text"></span>';
        button.querySelector(".k-text").textContent = option;
        button.addEventListener("click", function () {
          sendAnswer(option, false);
        });
        els.options.appendChild(button);
      });
    } else {
      clearMapHighlight();
    }

    startTimer(q.seconds, q.remaining !== undefined ? q.remaining : q.seconds);
    show(hasAnswered ? "answered" : "question");
  }

  function renderResult(r) {
    stopTimer();
    els.meScore.textContent = r.score;
    els.themScore.textContent = r.opponentScore;
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
    els.resultOpponent.textContent = r.opponentCorrect
      ? "Tegenstander: goed, +" + r.opponentPoints
      : "Tegenstander: fout of te laat";
    show("result");
  }

  function renderFinished(data) {
    stopTimer();
    els.meScore.textContent = data.score;
    els.themScore.textContent = data.opponentScore;

    if (data.outcome === "gewonnen") {
      els.finalTitle.textContent = "Gewonnen!";
    } else if (data.outcome === "verloren") {
      els.finalTitle.textContent = "Verloren";
    } else {
      els.finalTitle.textContent = "Gelijkspel";
    }
    els.finalScore.textContent = data.score + " – " + data.opponentScore;
    els.finalCorrect.textContent = data.correct + " van de " + data.questions + " vragen goed";

    if (data.rating === undefined) {
      els.finalRating.textContent = "";
    } else if (data.rated === false) {
      els.finalRating.textContent = data.rating + " elo (dit duel telde niet mee)";
    } else {
      const change = data.ratingChange;
      els.finalRating.textContent =
        data.rating + " elo (" + (change >= 0 ? "+" : "") + change + ")";
      els.finalRating.classList.toggle("up", change > 0);
      els.finalRating.classList.toggle("down", change < 0);
    }
    els.finalXp.textContent = data.xpEarned
      ? "+" + data.xpEarned + " XP · level " + data.level
      : "";
    show("finished");
  }

  function startCountdown(seconds, name) {
    if (countdownInterval) clearInterval(countdownInterval);
    let left = seconds;
    els.countdownName.textContent = name ? name + " doet mee!" : "Tegenstander gevonden!";
    els.countdownValue.textContent = left;
    show("countdown");
    countdownInterval = setInterval(function () {
      left -= 1;
      els.countdownValue.textContent = Math.max(0, left);
      if (left <= 0) clearInterval(countdownInterval);
    }, 1000);
  }

  // ------------------------------------------------------------------
  // Socket-events
  // ------------------------------------------------------------------
  socket.on("connect", function () {
    socket.emit("duelJoin", { code: DUEL.code });
  });

  socket.on("duelState", function (state) {
    setScores(state.me, state.opponent);
    if (state.state === "lobby") {
      els.waitingText.textContent = state.opponent
        ? "Wachten tot je tegenstander het scherm opent..."
        : "Zodra iemand meedoet, begint het duel vanzelf.";
      show("waiting");
    } else if (state.state === "question") {
      renderQuestion(state.question, state.answered);
    } else if (state.state === "reveal") {
      renderResult(state.result);
    } else if (state.state === "finished") {
      renderFinished(state.result);
    }
  });

  socket.on("duelStarting", function (data) {
    startCountdown(data.seconds || 3, els.themName.textContent);
  });
  socket.on("duelQuestion", function (q) {
    renderQuestion(q, false);
  });
  socket.on("duelReveal", renderResult);
  socket.on("duelFinished", renderFinished);

  socket.on("duelOpponentAnswered", function () {
    if (hasAnswered) {
      els.answeredText.textContent = "Je tegenstander heeft ook geantwoord...";
    }
  });

  socket.on("duelOpponentLeft", function (data) {
    showError((data.name || "Je tegenstander") + " is weggevallen. Het duel loopt door op de klok.");
  });

  socket.on("duelAnswerRejected", function () {
    hasAnswered = true;
    show("answered");
  });

  socket.on("duelError", function (data) {
    showError(data.message || "Er ging iets mis.");
    if (data.fatal) {
      setTimeout(function () {
        window.location.href = "/duel";
      }, 2500);
    }
  });
})();
