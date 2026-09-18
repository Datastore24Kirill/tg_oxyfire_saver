const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

async function api(path, opts = {}) {
  const r = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
    body: opts.body != null ? JSON.stringify(opts.body) : undefined,
  });
  return r.json();
}

const queueEl = $("#queue");
const emptyEl = $("#empty");
const inputEl = $("#urlInput");
const accountEl = $("#account");
const appVersionEl = $("#appVersion");
const aboutVersionEl = $("#aboutVersion");
const outDirHintEl = $("#outDirHint");
const dataDirHintEl = $("#dataDirHint");

const outDirEl = $("#outDir");
const toastEl = $("#toast");
const loginEl = $("#login");
const loginPhone = $("#loginPhone");
const loginCode = $("#loginCode");
const loginPassword = $("#loginPassword");
const loginBtn = $("#loginBtn");
const loginHint = $("#loginHint");
const loginError = $("#loginError");
const qrBlock = $("#qrBlock");
const phoneBlock = $("#phoneBlock");
const qrImg = $("#qrImg");
const qrPlaceholder = $("#qrPlaceholder");
const btnPassword = $("#btnPassword");
const clipToggle = $("#clipToggle");
const watchMaster = $("#watchMaster");

let toastTimer = null;
let authStep = "qr";
let loginBusy = false;
let lastQr = "";
let lastAuth = "";
let historyTimer = null;
let lastQueueKey = "";
let lastSettingsKey = "";
let lastPauseLabel = "";
let lastClip = null;
let lastWatchMaster = null;
let lastTg = "";
let wizardOpen = false;
let updateUrl = "";

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme === "light" ? "light" : "dark";
}

function settingsPayload() {
  return {
    media_filter: $("#setFilter").value,
    filename_template: $("#setTemplate").value,
    out_dir: $("#setOutDir").value,
    notify_on_done: $("#setNotify").checked,
    watch_hours: $("#setWatchHours").value.trim(),
    ui_lang: $("#setLang")?.value === "en" ? "en" : "ru",
    ui_theme: $("#setTheme")?.value === "light" ? "light" : "dark",
    download_concurrency: Number($("#setConcurrency")?.value || 2),
    proxy_enabled: !!$("#setProxyOn")?.checked,
    proxy_type: $("#setProxyType")?.value || "socks5",
    proxy_host: $("#setProxyHost")?.value.trim() || "",
    proxy_port: Number($("#setProxyPort")?.value || 0),
    proxy_username: $("#setProxyUser")?.value || "",
    proxy_password: $("#setProxyPass")?.value || "",
    proxy_secret: $("#setProxySecret")?.value || "",
  };
}

async function openExternal(url) {
  try {
    if (window.pywebview?.api?.open_url) {
      await window.pywebview.api.open_url(url);
      return;
    }
  } catch (_) {}
  window.open(url, "_blank");
}

function toast(msg) {
  toastEl.hidden = false;
  toastEl.textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastEl.hidden = true), 2800);
}

function setErr(msg) {
  loginError.hidden = !msg;
  loginError.textContent = msg || "";
}

function statusLabel(s) {
  const map = {
    queued: "status.queued",
    downloading: "status.downloading",
    paused: "status.paused",
    done: "status.done",
    error: "status.error",
    cancelled: "status.cancelled",
    skipped: "status.skipped",
  };
  return map[s] ? t(map[s]) : s;
}

function applyLangFromSettings(s) {
  const lang = s?.ui_lang === "en" ? "en" : "ru";
  if (window.I18N.lang !== lang) {
    window.I18N.setLang(lang);
    lastPauseLabel = "";
    lastQueueKey = "";
  } else {
    window.I18N.apply();
  }
  const sel = $("#setLang");
  if (sel && document.activeElement !== sel) sel.value = lang;
}

function showQr(png) {
  if (png && png !== lastQr) {
    lastQr = png;
    qrImg.src = png;
  }
  qrImg.hidden = !png;
  qrPlaceholder.hidden = !!png;
}

function showLogin(state) {
  const s = state.auth_state || (state.ready ? "ready" : "qr");
  authStep = s;
  if (state.login_error) setErr(state.login_error);
  else if (!loginBusy) setErr("");

  if (s === "ready") {
    loginEl.hidden = true;
    loginBusy = false;
    return;
  }
  loginEl.hidden = false;

  if (s === "connecting") {
    loginHint.textContent = t("login.hint.connecting");
    showQr(null);
    return;
  }
  if (s === "qr") {
    loginHint.textContent = t("login.hint.qr_short");
    qrBlock.hidden = false;
    phoneBlock.hidden = true;
    loginPassword.hidden = true;
    btnPassword.hidden = true;
    showQr(state.qr_png || null);
    return;
  }
  if (s === "password") {
    qrBlock.hidden = true;
    phoneBlock.hidden = true;
    loginPassword.hidden = false;
    btnPassword.hidden = false;
    loginHint.textContent = t("login.hint.password");
    if (lastAuth !== s) toast(t("toast.need_2fa"));
    lastAuth = s;
    return;
  }
  if (s === "login" || s === "code") {
    qrBlock.hidden = true;
    phoneBlock.hidden = false;
    loginPassword.hidden = true;
    btnPassword.hidden = true;
    loginPhone.hidden = s !== "login";
    loginCode.hidden = s !== "code";
    loginBtn.textContent = loginBusy
      ? t("login.waiting")
      : s === "code"
        ? t("login.sign_in")
        : t("login.get_code");
    loginHint.textContent =
      s === "code" ? t("login.hint.code") : t("login.hint.phone");
    if (lastAuth !== s && s === "code") toast(t("toast.code_sent"));
    lastAuth = s;
  }
}

async function onLoginSubmit() {
  if (loginBusy) return;
  loginBusy = true;
  setErr("");
  try {
    let res;
    if (authStep === "login") {
      res = await api("/auth/send_code", { method: "POST", body: { phone: loginPhone.value.trim() } });
    } else if (authStep === "code") {
      res = await api("/auth/sign_code", { method: "POST", body: { code: loginCode.value.trim() } });
    }
    if (res && !res.ok) setErr(res.error || t("toast.error"));
  } catch (e) {
    setErr(String(e));
  } finally {
    loginBusy = false;
  }
}

async function onPassword() {
  if (loginBusy) return;
  loginBusy = true;
  setErr("");
  btnPassword.disabled = true;
  btnPassword.textContent = t("login.checking");
  try {
    const res = await api("/auth/sign_password", {
      method: "POST",
      body: { password: loginPassword.value },
    });
    if (res && !res.ok) setErr(res.error || t("toast.bad_password"));
    else toast(t("toast.logged_in"));
  } catch (e) {
    setErr(String(e));
  } finally {
    loginBusy = false;
    btnPassword.disabled = false;
    btnPassword.textContent = t("login.confirm_password");
  }
}

function renderQueue(jobs) {
  emptyEl.style.display = jobs.length ? "none" : "block";
  const ordered = [...jobs].reverse();
  const seen = new Set();

  for (const job of ordered) {
    seen.add(job.id);
    let card = queueEl.querySelector(`[data-job-id="${job.id.replace(/"/g, "")}"]`);
    const mb =
      job.total_mb > 0
        ? `${job.received_mb.toFixed(1)}/${job.total_mb.toFixed(1)} ${t("mb")}`
        : "";
    const sub = [job.channel || job.peer_label, job.media_type, mb, job.error, job.source]
      .filter(Boolean)
      .join(" · ");
    const prog = Math.min(100, job.progress || 0);
    const badge = statusLabel(job.status);

    if (!card) {
      card = document.createElement("article");
      card.className = "card";
      card.dataset.jobId = job.id;
      card.innerHTML = `
      <div class="card-row">
        <div class="thumb-slot"></div>
        <div class="meta" style="flex:1;min-width:0">
          <div class="url"></div>
          <div class="sub"></div>
          <div class="bar"><i></i></div>
        </div>
        <div class="badge"></div>
      </div>
      <div class="card-actions"></div>`;
      queueEl.prepend(card);
    }

    // Превью: обновлять когда появилось / сменилось
    const slot = card.querySelector(".thumb-slot");
    const thumbKey = job.thumb
      ? `${job.thumb.length}:${job.thumb.slice(22, 42)}`
      : "";
    if (slot && card.dataset.thumbKey !== thumbKey) {
      card.dataset.thumbKey = thumbKey;
      slot.innerHTML = "";
      if (job.thumb) {
        const img = document.createElement("img");
        img.className = "thumb";
        img.alt = "";
        img.src = job.thumb;
        slot.appendChild(img);
      } else {
        const ph = document.createElement("div");
        ph.className = "thumb";
        slot.appendChild(ph);
      }
    }

    card.querySelector(".url").textContent = job.url || "";
    card.querySelector(".sub").textContent = sub || "…";
    card.querySelector(".bar > i").style.width = `${prog}%`;
    const badgeEl = card.querySelector(".badge");
    badgeEl.className = `badge ${job.status}`;
    badgeEl.textContent = badge;

    // кнопки только при смене статуса
    if (card.dataset.status !== job.status || card.dataset.path !== (job.path || "")) {
      card.dataset.status = job.status;
      card.dataset.path = job.path || "";
      const actions = card.querySelector(".card-actions");
      actions.innerHTML = "";
      if (job.status === "queued") {
        actions.append(btn(t("btn.pause"), () => api("/job/pause", { method: "POST", body: { id: job.id } })));
      }
      if (job.status === "paused" || job.status === "error" || job.status === "cancelled" || job.status === "skipped") {
        actions.append(
          btn(t("btn.resume"), async () => {
            const res = await api("/job/resume", { method: "POST", body: { id: job.id } });
            if (!res.ok) toast(res.error || t("toast.resume_fail"));
            else toast(t("toast.requeued"));
          })
        );
      }
      if (job.status === "downloading" || job.status === "queued" || job.status === "paused") {
        actions.append(btn(t("btn.cancel"), () => api("/job/cancel", { method: "POST", body: { id: job.id } })));
      }
      if (job.status === "done" && job.path) {
        actions.append(
          btn(t("btn.finder"), () => api("/reveal", { method: "POST", body: { path: job.path } }))
        );
      }
      actions.append(btn(t("btn.remove"), () => api("/job/remove", { method: "POST", body: { id: job.id } })));
    }

    // Клик по превью → Finder для готовых
    const thumbEl = card.querySelector(".thumb");
    if (thumbEl && job.status === "done" && job.path) {
      thumbEl.style.cursor = "pointer";
      thumbEl.title = t("btn.finder");
      thumbEl.onclick = () => api("/reveal", { method: "POST", body: { path: job.path } });
    }
  }

  [...queueEl.querySelectorAll(".card")].forEach((card) => {
    if (!seen.has(card.dataset.jobId)) card.remove();
  });
}

function queueKey(jobs) {
  return (jobs || [])
    .map((j) =>
      [
        j.id,
        j.status,
        Math.round(j.progress || 0),
        (j.received_mb || 0).toFixed(1),
        j.error || "",
        j.path || "",
        j.thumb ? "1" : "0",
      ].join(":")
    )
    .join("|");
}

function renderWatchers(list, master) {
  watchMaster.checked = !!master;
  const el = $("#watchersList");
  el.innerHTML = "";
  if (!list.length) {
    el.innerHTML = `<div class="empty"><div>${t("watchers.empty")}</div></div>`;
    return;
  }
  for (const w of list) {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <div class="card-top">
        <div class="meta">
          <div class="url">${esc(w.title || w.peer_key)}</div>
          <div class="sub">${esc(w.peer_key)} · ${t("filter_label")} ${esc(w.media_filter || "—")} · last ${w.last_msg_id || 0}</div>
        </div>
        <label class="switch-row" style="width:auto;padding:6px 10px">
          <span>${w.enabled ? t("watchers.on") : t("watchers.off")}</span>
          <input type="checkbox" ${w.enabled ? "checked" : ""} data-peer="${esc(w.peer_key)}" class="w-en" />
        </label>
      </div>
      <div class="card-actions"></div>`;
    card.querySelector(".card-actions").append(
      btn(t("btn.remove"), () =>
        api("/watchers/delete", { method: "POST", body: { peer_key: w.peer_key } }).then(loadWatchers)
      )
    );
    card.querySelector(".w-en").addEventListener("change", async (e) => {
      await api("/watchers/enable", {
        method: "POST",
        body: { peer_key: w.peer_key, enabled: e.target.checked },
      });
    });
    el.appendChild(card);
  }
}

async function loadWatchers() {
  const st = await api("/state");
  renderWatchers(st.watchers || [], st.watchers_master);
}

async function loadHistory() {
  const q = $("#historyQuery").value.trim();
  const data = await api("/history?q=" + encodeURIComponent(q));
  const el = $("#historyList");
  el.innerHTML = "";
  const items = data.items || [];
  if (!items.length) {
    el.innerHTML = `<div class="empty"><div>${t("history.empty")}</div></div>`;
    return;
  }
  for (const h of items) {
    const card = document.createElement("article");
    card.className = "card";
    const thumbHtml = h.thumb
      ? `<img class="thumb" alt="" src="${h.thumb}" />`
      : `<div class="thumb"></div>`;
    card.innerHTML = `
      <div class="card-row">
        ${thumbHtml}
        <div class="meta" style="flex:1;min-width:0">
          <div class="url">${esc(h.channel || h.peer_key)} · #${h.msg_id}</div>
          <div class="sub">${esc([h.media_type, h.status, h.path, h.error].filter(Boolean).join(" · "))}</div>
        </div>
        <div class="badge ${h.status}">${esc(statusLabel(h.status) || h.status)}</div>
      </div>
      <div class="card-actions"></div>`;
    const actions = card.querySelector(".card-actions");
    if (h.path) {
      const finderBtn = btn(t("btn.finder"), () =>
        api("/reveal", { method: "POST", body: { path: h.path } })
      );
      finderBtn.classList.add("primary");
      actions.append(finderBtn);
      const thumb = card.querySelector(".thumb");
      if (thumb) {
        thumb.style.cursor = "pointer";
        thumb.title = t("btn.finder");
        thumb.addEventListener("click", () =>
          api("/reveal", { method: "POST", body: { path: h.path } })
        );
      }
    }
    actions.append(
      btn(t("btn.retry"), async () => {
        await api("/history/retry", {
          method: "POST",
          body: { peer_key: h.peer_key, msg_id: h.msg_id, url: h.url || "" },
        });
        toast(t("toast.queued"));
        showTab("queue");
      })
    );
    el.appendChild(card);
  }
}

function fillSettings(s) {
  if (!s) return;
  applyLangFromSettings(s);
  applyTheme(s.ui_theme);
  $("#setFilter").value = s.media_filter || "video";
  $("#setTemplate").value = s.filename_template || "{channel}_{id}_{type}";
  $("#setOutDir").value = s.out_dir || "";
  $("#setNotify").checked = !!s.notify_on_done;
  $("#setWatchHours").value = s.watch_hours || "";
  if ($("#setTheme")) $("#setTheme").value = s.ui_theme === "light" ? "light" : "dark";
  if ($("#setConcurrency")) $("#setConcurrency").value = String(s.download_concurrency || 2);
  if ($("#setProxyOn")) $("#setProxyOn").checked = !!s.proxy_enabled;
  if ($("#setProxyType")) $("#setProxyType").value = s.proxy_type || "socks5";
  if ($("#setProxyHost")) $("#setProxyHost").value = s.proxy_host || "";
  if ($("#setProxyPort")) $("#setProxyPort").value = s.proxy_port ? String(s.proxy_port) : "";
  if ($("#setProxyUser")) $("#setProxyUser").value = s.proxy_username || "";
  if ($("#setProxyPass")) $("#setProxyPass").value = s.proxy_password || "";
  if ($("#setProxySecret")) $("#setProxySecret").value = s.proxy_secret || "";
  clipToggle.checked = !!s.clipboard_mode;
}

function showTab(name) {
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => {
    t.hidden = t.id !== "tab-" + name;
  });
  if (name === "history") loadHistory();
  if (name === "watchers") loadWatchers();
}

function btn(label, fn) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "btn tiny";
  b.textContent = label;
  b.addEventListener("click", fn);
  return b;
}

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function tick() {
  try {
    const state = await api("/state");
    showLogin(state);
    if (appVersionEl && state.version) appVersionEl.textContent = `v${state.version}`;
    if (aboutVersionEl && state.version) aboutVersionEl.textContent = `v${state.version}`;
    const tgEl = $("#tgStatus");
    if (tgEl) {
      const st = state.tg_status || "offline";
      const label = t(st === "online" ? "tg.online" : st === "reconnecting" ? "tg.reconnecting" : "tg.offline");
      const key = st + label;
      if (key !== lastTg) {
        lastTg = key;
        tgEl.textContent = label;
        tgEl.className = `tg-status ${st}`;
      }
    }
    const perr = $("#proxyError");
    if (perr) {
      if (state.proxy_error) {
        perr.hidden = false;
        perr.textContent = state.proxy_error;
      } else {
        perr.hidden = true;
      }
    }
    if (state.ready) {
      accountEl.textContent = state.account || "OK";
      outDirEl.textContent = state.out_dir || "—";
      if (outDirHintEl) outDirHintEl.textContent = state.out_dir || "—";
      if (dataDirHintEl && state.data_dir) dataDirHintEl.textContent = state.data_dir;
      const st = state.stats || {};
      $("#statQueued").textContent = st.queued || 0;
      $("#statActive").textContent = st.active || 0;
      $("#statDone").textContent = st.done || 0;

      const qk = queueKey(state.jobs || []);
      if (qk !== lastQueueKey) {
        lastQueueKey = qk;
        renderQueue(state.jobs || []);
      }

      const sk = JSON.stringify(state.settings || {});
      if (sk !== lastSettingsKey) {
        lastSettingsKey = sk;
        fillSettings(state.settings);
      }

      const pauseLabel = state.paused ? t("side.resume") : t("side.pause");
      if (pauseLabel !== lastPauseLabel) {
        lastPauseLabel = pauseLabel;
        $("#btnPauseGlobal").textContent = pauseLabel;
      }

      const clip = !!state.clipboard_mode;
      if (clip !== lastClip && document.activeElement !== clipToggle) {
        lastClip = clip;
        clipToggle.checked = clip;
      }
      const wm = !!state.watchers_master;
      if (wm !== lastWatchMaster && document.activeElement !== watchMaster) {
        lastWatchMaster = wm;
        watchMaster.checked = wm;
      }
      const wiz = $("#wizard");
      if (wiz && state.settings && !state.settings.onboarding_done && !wizardOpen) {
        wizardOpen = true;
        $("#wizLang").value = state.settings.ui_lang === "en" ? "en" : "ru";
        $("#wizTheme").value = state.settings.ui_theme === "light" ? "light" : "dark";
        $("#wizFolder").value = state.out_dir || state.settings.out_dir || "";
        wiz.hidden = false;
        window.I18N?.apply();
      }
    }
  } catch (e) {
    console.error(e);
  }
}

function bind() {
  $$(".nav-btn").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("#btnAdd").addEventListener("click", async () => {
    const text = inputEl.value.trim();
    if (!text) return toast(t("toast.paste_link"));
    const res = await api("/add", { method: "POST", body: { text } });
    if (!res.ok) return toast(res.error || t("toast.error"));
    inputEl.value = "";
    toast(`${t("toast.queued")}: ${res.count || res.ids?.length || 0}`);
  });
  $("#btnOpenFolder").addEventListener("click", () => api("/open_folder", { method: "POST", body: {} }));

  async function pickAndSetFolder() {
    let path = null;
    try {
      if (window.pywebview?.api?.pick_folder) {
        path = await window.pywebview.api.pick_folder();
      }
    } catch (_) {}
    if (!path) return;
    $("#setOutDir").value = path;
    outDirEl.textContent = path;
    if (outDirHintEl) outDirHintEl.textContent = path;
    const res = await api("/settings", { method: "POST", body: { out_dir: path } });
    if (res?.ok === false) return toast(res.error || t("toast.folder_fail"));
    toast(t("toast.folder_updated"));
  }
  $("#btnPickFolder")?.addEventListener("click", pickAndSetFolder);
  $("#btnPickFolderSettings")?.addEventListener("click", pickAndSetFolder);

  $("#btnClear").addEventListener("click", () => api("/clear_finished", { method: "POST", body: {} }));
  $("#btnPauseGlobal").addEventListener("click", async () => {
    const st = await api("/state");
    await api("/pause", { method: "POST", body: { paused: !st.paused } });
  });
  clipToggle.addEventListener("change", async () => {
    await api("/settings", { method: "POST", body: { clipboard_mode: clipToggle.checked } });
    toast(clipToggle.checked ? t("toast.clip_on") : t("toast.clip_off"));
  });
  watchMaster.addEventListener("change", async () => {
    await api("/settings", { method: "POST", body: { watchers_master: watchMaster.checked } });
  });
  $("#btnAddWatcher").addEventListener("click", async () => {
    const text = $("#watcherInput").value.trim();
    if (!text) return;
    const res = await api("/watchers/add", { method: "POST", body: { text } });
    if (!res.ok) return toast(res.error || t("toast.error"));
    $("#watcherInput").value = "";
    toast(t("toast.watcher_added"));
    loadWatchers();
  });
  $("#btnStopWatchers").addEventListener("click", async () => {
    await api("/watchers/stop_all", { method: "POST", body: {} });
    toast(t("toast.watchers_stopped"));
    loadWatchers();
  });
  $("#historyQuery").addEventListener("input", () => {
    clearTimeout(historyTimer);
    historyTimer = setTimeout(loadHistory, 250);
  });
  $("#setLang")?.addEventListener("change", async () => {
    const lang = $("#setLang").value === "en" ? "en" : "ru";
    window.I18N.setLang(lang);
    lastPauseLabel = "";
    lastQueueKey = "";
    await api("/settings", { method: "POST", body: { ui_lang: lang } });
    toast(t("toast.lang_saved"));
    tick();
  });
  $("#btnSaveSettings").addEventListener("click", async () => {
    await api("/settings", { method: "POST", body: settingsPayload() });
    applyTheme($("#setTheme")?.value);
    toast(t("toast.saved"));
  });
  $("#setTheme")?.addEventListener("change", () => applyTheme($("#setTheme").value));
  $("#btnExport")?.addEventListener("click", async () => {
    const data = await api("/settings/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "tg-oxyfire-saver-settings.json";
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $("#btnImport")?.addEventListener("click", () => $("#importFile")?.click());
  $("#importFile")?.addEventListener("change", async () => {
    const file = $("#importFile").files?.[0];
    $("#importFile").value = "";
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      const res = await api("/settings/import", { method: "POST", body: data });
      if (!res.ok) return toast(res.error || t("toast.import_fail"));
      lastSettingsKey = "";
      toast(t("toast.imported"));
      tick();
    } catch (_) {
      toast(t("toast.import_fail"));
    }
  });
  $("#btnUpdate")?.addEventListener("click", () => {
    if (updateUrl) openExternal(updateUrl);
  });
  $("#btnWizFolder")?.addEventListener("click", async () => {
    let path = null;
    try {
      if (window.pywebview?.api?.pick_folder) path = await window.pywebview.api.pick_folder();
    } catch (_) {}
    if (path) $("#wizFolder").value = path;
  });
  $("#wizLang")?.addEventListener("change", () => {
    window.I18N.setLang($("#wizLang").value === "en" ? "en" : "ru");
  });
  $("#wizTheme")?.addEventListener("change", () => applyTheme($("#wizTheme").value));
  $("#btnWizDone")?.addEventListener("click", async () => {
    const lang = $("#wizLang").value === "en" ? "en" : "ru";
    const theme = $("#wizTheme").value === "light" ? "light" : "dark";
    window.I18N.setLang(lang);
    applyTheme(theme);
    const body = {
      ui_lang: lang,
      ui_theme: theme,
      onboarding_done: true,
    };
    const folder = $("#wizFolder").value.trim();
    if (folder) body.out_dir = folder;
    await api("/settings", { method: "POST", body });
    $("#wizard").hidden = true;
    lastSettingsKey = "";
    toast(t("toast.saved"));
  });
  $("#btnLogout").addEventListener("click", async () => {
    if (!confirm(t("toast.logout_confirm"))) return;
    toast(t("toast.logging_out"));
    const res = await api("/auth/logout", { method: "POST", body: {} });
    if (!res.ok) return toast(res.error || t("toast.logout_fail"));
    toast(t("toast.login_again"));
    lastAuth = "";
    tick();
  });
  const btnAbout = $("#btnAboutPanel");
  if (btnAbout) {
    btnAbout.addEventListener("click", async () => {
      try {
        if (window.pywebview?.api?.show_about) {
          await window.pywebview.api.show_about();
          return;
        }
      } catch (_) {}
      // fallback: открыть первую ссылку / показать alert
      window.open("https://3dwolf.ru", "_blank");
    });
  }
  document.querySelectorAll(".about-links a").forEach((a) => {
    a.addEventListener("click", async (e) => {
      e.preventDefault();
      const url = a.getAttribute("href");
      try {
        if (window.pywebview?.api?.open_url) {
          await window.pywebview.api.open_url(url);
          return;
        }
      } catch (_) {}
      window.open(url, "_blank");
    });
  });
  $("#btnRefreshQr").addEventListener("click", () => api("/auth/qr/refresh", { method: "POST", body: {} }));
  $("#btnPhoneInstead").addEventListener("click", () => api("/auth/phone", { method: "POST", body: {} }));
  $("#btnQrInstead").addEventListener("click", () => api("/auth/qr", { method: "POST", body: {} }));
  loginBtn.addEventListener("click", onLoginSubmit);
  btnPassword.addEventListener("click", onPassword);
  setInterval(tick, 500);
  tick();
  checkUpdate();
  setInterval(checkUpdate, 6 * 60 * 60 * 1000);
}

async function checkUpdate() {
  try {
    const info = await api("/update");
    const banner = $("#updateBanner");
    if (!banner) return;
    if (info?.newer && info.url) {
      updateUrl = info.url;
      $("#updateText").textContent = `${t("update.available")}: v${info.latest}`;
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  } catch (_) {}
}

window.I18N?.apply();
bind();
