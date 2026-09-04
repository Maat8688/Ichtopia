/* Bord (docent) voor de klassikale quiz. */
(function () {
  const socket = io();

  const sections = {
    lobby: document.getElementById("lobby"),
    question: document.getElementById("question"),
    reveal: document.getElementById("reveal"),
    finished: document.getElementById("finished"),
  };

  const els = {
    questionCounter: document.getElementById("questionCounter"),
    playerCount: document.getElementById("playerCount"),
    playerList: document.getElementById("playerList"),
    startBtn: document.getElementById("startBtn"),
    timer: document.getElementById("timer"),
    timerValue: document.getElementById("timerValue"),
    prompt: document.getElementById("prompt"),
    answeredCount: document.getElementById("answeredCount"),
    boardBody: document.getElementById("boardBody"),
    options: document.getElementById("options"),
    skipBtn: document.getElementById("skipBtn"),
    correctAnswer: document.getElementById("correctAnswer"),
    chart: document.getElementById("chart"),
    noAnswer: document.getElementById("noAnswer"),
    leaderboard: document.getElementById("leaderboard"),
    nextBtn: document.getElementById("nextBtn"),
    podium: document.getElementById("podium"),
    finalLeaderboard: document.getElementById("finalLeaderboard"),
    error: document.getElementById("error"),
  };

  let timerInterval = null;
  let players = [];

  function hostData(extra) {
    return Object.assign({ pin: KAHOOT.pin, token: KAHOOT.token }, extra || {});
  }

  function show(name) {
    Object.keys(sections).forEach((key) => {
      sections[key].classList.toggle("hidden", key !== name);
    });
    els.questionCounter.classList.toggle("hidden", name === "lobby");
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.classList.remove("hidden");
    setTimeout(() => els.error.classList.add("hidden"), 5000);
  }

  // ------------------------------------------------------------------
  // Kaart
  // ------------------------------------------------------------------
  // Er staan twee kaarten op de pagina (vraag en onthulling), dus altijd binnen een sectie zoeken.
  function clearMapHighlight(root) {
    root.querySelectorAll("#questions > g").forEach((g) => {
      g.classList.remove("active", "k-correct");
      g.setAttribute("state", "Normal");
    });
  }

  function highlightMap(root, mapId, category, className) {
    clearMapHighlight(root);
    if (!mapId) return;
    let selector = '#questions > g[id="' + mapId + '"]';
    if (category) selector += "." + category;
    const element = root.querySelector(selector) || root.querySelector('#questions > g[id="' + mapId + '"]');
    if (element) element.classList.add(className);
  }

  // ------------------------------------------------------------------
  // Timer
  // ------------------------------------------------------------------
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
  // Lobby
  // ------------------------------------------------------------------
  function renderPlayers(data) {
    players = data.players || [];
    els.playerCount.textContent = data.connected;
    els.playerList.innerHTML = "";
    if (players.length === 0) {
      els.playerList.innerHTML = '<p class="k-muted k-pulse">Wachten op spelers...</p>';
    }
    players.forEach((player) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "k-player-chip" + (player.connected ? "" : " offline");
      chip.textContent = player.name;
      chip.title = "Verwijder " + player.name;
      chip.addEventListener("click", () => {
        if (confirm(player.name + " uit de quiz verwijderen?")) {
          socket.emit("kahootKick", hostData({ playerId: player.id }));
        }
      });
      els.playerList.appendChild(chip);
    });
    els.startBtn.disabled = data.connected === 0;
  }

  // ------------------------------------------------------------------
  // Vraag
  // ------------------------------------------------------------------
  function renderQuestion(q) {
    show("question");
    els.questionCounter.textContent = "Vraag " + q.number + " / " + q.total;
    els.prompt.textContent = q.prompt;
    els.answeredCount.textContent = "0";
    els.options.innerHTML = "";

    if (q.mode === 1) {
      els.boardBody.classList.remove("single");
      els.options.classList.remove("hidden");
      highlightMap(sections.question, q.mapId, q.category, "active");
      q.options.forEach((option, i) => {
        const card = document.createElement("div");
        card.className = "k-option";
        card.dataset.color = i % 4;
        card.dataset.answer = option;
        card.innerHTML = '<span class="k-shape"></span><span class="k-text"></span>';
        card.querySelector(".k-text").textContent = option;
        els.options.appendChild(card);
      });
    } else {
      // Klik-modus: de kaart staat op het bord, maar zonder hint waar het is.
      els.boardBody.classList.add("single");
      els.options.classList.add("hidden");
      clearMapHighlight(sections.question);
    }

    startTimer(q.seconds, q.remaining !== undefined ? q.remaining : q.seconds);
  }

  // ------------------------------------------------------------------
  // Onthulling
  // ------------------------------------------------------------------
  function renderLeaderboard(list, entries, limit) {
    list.innerHTML = "";
    entries.slice(0, limit || entries.length).forEach((entry, i) => {
      const li = document.createElement("li");
      li.style.animationDelay = i * 0.08 + "s";
      const delta = entry.lastPoints > 0 ? "+" + entry.lastPoints : "+0";
      li.innerHTML =
        '<span class="k-rank"></span><span class="k-name"></span>' +
        '<span class="k-delta"></span><span class="k-score"></span>';
      li.querySelector(".k-rank").textContent = entry.rank;
      li.querySelector(".k-name").textContent = entry.name;
      const deltaEl = li.querySelector(".k-delta");
      deltaEl.textContent = delta;
      if (!entry.lastPoints) deltaEl.classList.add("zero");
      li.querySelector(".k-score").textContent = entry.score;
      list.appendChild(li);
    });
  }

  function renderReveal(r) {
    stopTimer();
    show("reveal");
    els.questionCounter.textContent = "Vraag " + r.number + " / " + r.total;
    els.correctAnswer.textContent = r.correctAnswer;
    highlightMap(sections.reveal, r.mapId, r.category, "k-correct");

    // Verdeling van antwoorden
    els.chart.innerHTML = "";
    const answered = r.distribution.reduce((sum, d) => sum + d.count, 0);
    const max = Math.max(1, ...r.distribution.map((d) => d.count));
    r.distribution.forEach((d, i) => {
      const bar = document.createElement("div");
      bar.className = "k-bar" + (d.correct ? " correct" : "") + (r.mode !== 1 && !d.correct ? " wrong" : "");
      bar.dataset.color = r.mode === 1 ? i % 4 : d.correct ? 3 : 0;
      bar.innerHTML =
        '<div class="k-bar-count"></div><div class="k-bar-track"><div class="k-bar-fill"></div></div>' +
        '<div class="k-bar-label"></div>';
      bar.querySelector(".k-bar-count").textContent = d.count;
      bar.querySelector(".k-bar-label").textContent = d.label + (d.correct ? " ✓" : "");
      const fill = bar.querySelector(".k-bar-fill");
      fill.style.height = "6px";
      els.chart.appendChild(bar);
      requestAnimationFrame(() => {
        fill.style.height = Math.max(6, (d.count / max) * 100) + "%";
      });
    });
    els.noAnswer.textContent =
      r.noAnswer > 0 ? r.noAnswer + " speler(s) gaven geen antwoord" : answered + " antwoorden";

    renderLeaderboard(els.leaderboard, r.leaderboard, 5);
    els.nextBtn.textContent = r.isLast ? "Eindstand" : "Volgende vraag";
  }

  // ------------------------------------------------------------------
  // Eindstand
  // ------------------------------------------------------------------
  function renderFinished(leaderboard) {
    stopTimer();
    show("finished");
    els.questionCounter.textContent = "Afgelopen";
    els.podium.innerHTML = "";
    const order = [1, 0, 2]; // tweede links, eerste in het midden, derde rechts
    order.forEach((index) => {
      const entry = leaderboard[index];
      if (!entry) return;
      const place = document.createElement("div");
      place.className = "k-podium-place";
      place.dataset.place = index + 1;
      place.innerHTML =
        '<div class="k-podium-name"></div>' +
        '<div class="k-podium-block">' + (index + 1) + '<span class="k-podium-score"></span></div>';
      place.querySelector(".k-podium-name").textContent = entry.name;
      place.querySelector(".k-podium-score").textContent = entry.score + " punten";
      els.podium.appendChild(place);
    });
    renderLeaderboard(els.finalLeaderboard, leaderboard);
    if (typeof confetti === "function") {
      confetti({ particleCount: 200, spread: 90, origin: { x: 0.5, y: 0.4 }, ticks: 300 });
    }
  }

  // ------------------------------------------------------------------
  // Socket-events
  // ------------------------------------------------------------------
  socket.on("connect", () => {
    socket.emit("kahootHost", hostData());
  });

  socket.on("kahootState", (state) => {
    renderPlayers(state.players);
    if (state.state === "lobby") {
      show("lobby");
    } else if (state.state === "question") {
      renderQuestion(state.question);
      els.answeredCount.textContent = state.answered.answered;
    } else if (state.state === "reveal") {
      renderReveal(state.reveal);
    } else if (state.state === "finished") {
      renderFinished(state.leaderboard);
    }
  });

  socket.on("kahootPlayers", renderPlayers);
  socket.on("kahootQuestion", renderQuestion);
  socket.on("kahootAnswerCount", (data) => {
    els.answeredCount.textContent = data.answered;
  });
  socket.on("kahootReveal", renderReveal);
  socket.on("kahootFinished", (data) => renderFinished(data.leaderboard));

  socket.on("kahootError", (data) => {
    showError(data.message || "Er ging iets mis.");
    if (data.fatal) {
      setTimeout(() => (window.location.href = "/host"), 3000);
    }
  });

  // ------------------------------------------------------------------
  // Knoppen
  // ------------------------------------------------------------------
  els.startBtn.addEventListener("click", () => {
    els.startBtn.disabled = true;
    socket.emit("kahootStart", hostData());
  });

  els.skipBtn.addEventListener("click", () => {
    socket.emit("kahootReveal", hostData());
  });

  els.nextBtn.addEventListener("click", () => {
    els.nextBtn.disabled = true;
    socket.emit("kahootNext", hostData());
    setTimeout(() => (els.nextBtn.disabled = false), 1000);
  });

  // Sneltoetsen voor de docent: spatie/enter = volgende, s = stop de tijd.
  document.addEventListener("keydown", (event) => {
    if (event.target.tagName === "INPUT") return;
    if (event.key === " " || event.key === "Enter") {
      if (!sections.reveal.classList.contains("hidden")) els.nextBtn.click();
      else if (!sections.lobby.classList.contains("hidden") && !els.startBtn.disabled) els.startBtn.click();
    } else if (event.key === "s" && !sections.question.classList.contains("hidden")) {
      els.skipBtn.click();
    }
  });
})();
