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
    } else if (btn.dataset.label) {
      btn.textContent = btn.dataset.label;
    }
    checkBtn.disabled = busy;
    subBtn.disabled = busy;
  }

  function validateCore(v) {
    if (!v.class_number) return "Enter a class number.";
    if (!/^\d+$/.test(v.class_number)) return "Class number must be digits only.";
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
    row(dl, "Current Status", data.status || "Unknown");
    row(dl, "Instructor", data.instructor);
    row(dl, "Room", data.room);
    row(dl, "Meets", data.days_and_times);
    resultEl.appendChild(dl);

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
