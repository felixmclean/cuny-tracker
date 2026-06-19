"use strict";

(function () {
  const form = document.getElementById("track-form");
  const checkBtn = document.getElementById("check-btn");
  const subBtn = document.getElementById("subscribe-btn");
  const messageEl = document.getElementById("message");
  const resultEl = document.getElementById("result");

  const fields = {
    class_number: document.getElementById("class_number"),
    institution: document.getElementById("institution"),
    term: document.getElementById("term"),
    year: document.getElementById("year"),
    session: document.getElementById("session"),
    email: document.getElementById("email"),
  };

  function values() {
    return {
      class_number: fields.class_number.value.trim(),
      institution: fields.institution.value,
      term: fields.term.value,
      year: fields.year.value,
      session: fields.session.value,
      email: fields.email.value.trim(),
    };
  }

  function showMessage(text, kind) {
    messageEl.textContent = text;
    messageEl.className = "message " + (kind || "info");
    messageEl.hidden = false;
  }

  function clearMessage() {
    messageEl.hidden = true;
    messageEl.textContent = "";
  }

  function setBusy(btn, busy, busyLabel) {
    if (busy) {
      btn.dataset.label = btn.textContent;
      btn.textContent = busyLabel;
      btn.disabled = true;
      checkBtn.disabled = true;
      subBtn.disabled = true;
    } else {
      if (btn.dataset.label) btn.textContent = btn.dataset.label;
      btn.disabled = false;
      checkBtn.disabled = false;
      subBtn.disabled = false;
    }
  }

  function statusClass(status) {
    const s = (status || "").toLowerCase();
    if (s.indexOf("open") !== -1) return "status-open";
    if (s.indexOf("wait") !== -1) return "status-wait";
    return "status-closed";
  }

  function validateCore(v) {
    if (!v.class_number) return "Enter a class number.";
    if (!/^\d+$/.test(v.class_number)) return "Class number must be digits only.";
    if (!v.institution) return "Pick an institution.";
    if (!v.term) return "Pick a term.";
    if (!v.year) return "Pick a year.";
    if (!v.session) return "Pick a session.";
    return null;
  }

  function row(dl, label, value) {
    if (value === undefined || value === null || value === "") return;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }

  function renderResult(data) {
    resultEl.innerHTML = "";

    const h = document.createElement("h3");
    h.textContent =
      [data.course_name, data.course_title].filter(Boolean).join(" ") || "Class";
    resultEl.appendChild(h);

    if (data.course_number) {
      const sub = document.createElement("p");
      sub.className = "sub";
      sub.textContent =
        "Class #" + data.course_number + " · " + data.institution +
        " · " + data.term + " " + data.year;
      resultEl.appendChild(sub);
    }

    const dl = document.createElement("dl");

    const dtS = document.createElement("dt");
    dtS.textContent = "Current Status";
    const ddS = document.createElement("dd");
    const pill = document.createElement("span");
    pill.className = "status-pill " + statusClass(data.status);
    pill.textContent = data.status || "Unknown";
    ddS.appendChild(pill);

    const isOpen = (data.status || "").toLowerCase() === "open";
    if (!isOpen && data.currently_enrolled && data.course_capacity) {
      const filled = document.createElement("div");
      filled.textContent =
        data.currently_enrolled + "/" + data.course_capacity + " seats filled";
      filled.style.marginTop = "4px";
      filled.style.fontSize = "0.9rem";
      filled.style.color = "var(--muted)";
      ddS.appendChild(filled);
    }

    dl.appendChild(dtS);
    dl.appendChild(ddS);

    row(dl, "Instructor", data.instructor);
    row(dl, "Room", data.room);
    row(dl, "Meets", data.days_and_times);
    resultEl.appendChild(dl);

    if (data.waitlist_capacity && data.waitlist_capacity !== "0") {
      const wl = document.createElement("p");
      wl.className = "fine";
      wl.textContent =
        "Waitlist: " + (data.currently_waitlisted || "0") + " / " +
        data.waitlist_capacity;
      resultEl.appendChild(wl);
    }

    resultEl.hidden = false;
  }

  async function checkStatus() {
    clearMessage();
    const v = values();
    const err = validateCore(v);
    if (err) {
      resultEl.hidden = true;
      showMessage(err, "err");
      return;
    }

    const qs = new URLSearchParams({
      class_number: v.class_number,
      institution: v.institution,
      term: v.term,
      year: v.year,
      session: v.session,
    });

    setBusy(checkBtn, true, "Checking…");
    try {
      const res = await fetch("/status?" + qs.toString(), {
        headers: { Accept: "application/json" },
      });
      const data = await res.json();
      if (data.found) {
        clearMessage();
        renderResult(data);
      } else {
        resultEl.hidden = true;
        showMessage(data.error || "No class found for those details.", "err");
      }
    } catch (e) {
      resultEl.hidden = true;
      showMessage("Network error. Check your connection and try again.", "err");
    } finally {
      setBusy(checkBtn, false);
    }
  }

  async function subscribe() {
    clearMessage();
    const v = values();
    const err = validateCore(v);
    if (err) {
      showMessage(err, "err");
      return;
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.email)) {
      showMessage("Enter a valid email address.", "err");
      fields.email.focus();
      return;
    }

    setBusy(subBtn, true, "Subscribing…");
    try {
      const res = await fetch("/subscribe", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          class_number: v.class_number,
          institution: v.institution,
          term: v.term,
          year: Number(v.year),
          session: v.session,
          email: v.email,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        showMessage(data.message || "You're subscribed.", data.already ? "info" : "ok");
      } else {
        showMessage(data.error || "Couldn't subscribe. Try again.", "err");
      }
    } catch (e) {
      showMessage("Network error. Check your connection and try again.", "err");
    } finally {
      setBusy(subBtn, false);
    }
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    checkStatus();
  });
  subBtn.addEventListener("click", function (e) {
    e.preventDefault();
    subscribe();
  });
})();
