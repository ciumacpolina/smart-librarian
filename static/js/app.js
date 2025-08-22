const form  = document.getElementById("form");
const input = document.getElementById("input");
const chat  = document.getElementById("chat");
const sendBtn = document.getElementById("send");
const autoSpeakCheckbox = document.getElementById("autoSpeak");
const micBtn = document.getElementById("micBtn");

// ----- Markdown -----
if (window.marked) {
  marked.setOptions({ mangle:false, headerIds:false, breaks:true });
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, m => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;"
  }[m]));
}

function renderBot(text) {
  if (window.marked && window.DOMPurify) {
    const html = marked.parse(text || "");
    return DOMPurify.sanitize(html);
  }
  return escapeHtml(text || "").replace(/\n/g, "<br>");
}

/* ===================== TTS: single-player registry ===================== */
const ttsPlayers = new Map(); 

function anyTTSPlaying() {
  for (const item of ttsPlayers.values()) {
    if (item && item.state === 'playing') return true;
  }
  return false;
}

async function fetchTTSBlob(text) {
  const clean = (text || "")
    .replace(/\*\*/g, "")
    .replace(/`+/g, "")
    .replace(/_/g, "");
  if (!clean.trim()) return null;

  const resp = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: clean })
  });
  if (!resp.ok) return null;
  return await resp.blob();
}

function stopAllOtherPlayers(exceptBtn) {
  for (const [btn, item] of ttsPlayers.entries()) {
    if (btn !== exceptBtn && item && item.audio) {
      try { item.lastTime = item.audio.currentTime; } catch (e) {}
      try { item.audio.pause(); } catch (e) {}
      item.state = 'paused';
      btn.textContent = '▶️';
    }
  }
}

// attach a controllable TTS to a button (toggle play/pause)
function attachTTS(btn, text) {
  btn.addEventListener('click', async () => {
    let item = ttsPlayers.get(btn);

    if (item && item.audio) {
      if (item.state === 'playing') {
        try { item.lastTime = item.audio.currentTime; } catch (e) {}
        item.audio.pause();
        return;
      }
      if (item.state === 'paused') {
        stopAllOtherPlayers(btn);
        item.audio.currentTime = item.lastTime || 0;
        item.audio.play();
        return;
      }
    }

    stopAllOtherPlayers(btn);
    btn.disabled = true;
    btn.textContent = '…';

    const blob = await fetchTTSBlob(text);
    if (!blob) {
      btn.textContent = '🔊';
      btn.disabled = false;
      return;
    }

    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);

    audio.addEventListener('play', () => {
      btn.textContent = '⏸';
      const it = ttsPlayers.get(btn);
      if (it) it.state = 'playing';
    });

    audio.addEventListener('pause', () => {
      if (!audio.ended) {
        const it = ttsPlayers.get(btn);
        if (it) {
          try { it.lastTime = audio.currentTime; } catch (e) {}
          it.state = 'paused';
        }
        btn.textContent = '▶️';
      }
    });

    audio.addEventListener('ended', () => {
      btn.textContent = '🔊';
      const it = ttsPlayers.get(btn);
      if (it) it.state = 'ended';
      try { URL.revokeObjectURL(url); } catch (e) {}
      ttsPlayers.delete(btn);
    });

    audio.addEventListener('error', () => {
      btn.textContent = '🔊';
      const it = ttsPlayers.get(btn);
      if (it) it.state = 'idle';
      try { URL.revokeObjectURL(url); } catch (e) {}
      ttsPlayers.delete(btn);
    });

    ttsPlayers.set(btn, { audio, state: 'loading', url, lastTime: 0 });
    btn.disabled = false;
    await audio.play().catch(() => {});
  });
}

async function ensureSingleTTSPlay(hostEl, text) {
  if (anyTTSPlaying()) return;

  let speakBtn = hostEl.querySelector('.speak-btn');
  if (!speakBtn) {
    speakBtn = document.createElement('button');
    speakBtn.className = 'speak-btn btn btn-sm btn-outline-secondary';
    speakBtn.textContent = '🔊';
    speakBtn.type = 'button';
    const line = document.createElement('div');
    line.style.marginTop = '6px';
    line.appendChild(speakBtn);
    hostEl.appendChild(line);
    attachTTS(speakBtn, text);
  }
  speakBtn.click();
}

function addSpeakButtonToMessage(messageEl, text) {
  if (!messageEl) return;
  if (messageEl.querySelector('.speak-btn')) return;

  const btn = document.createElement('button');
  btn.className = 'speak-btn btn btn-sm btn-outline-secondary';
  btn.textContent = '🔊';
  btn.title = 'Play / Pause';
  btn.style.marginLeft = '8px';
  btn.type = 'button';

  const line = document.createElement('div');
  line.style.marginTop = '6px';
  line.appendChild(btn);
  messageEl.appendChild(line);

  attachTTS(btn, text);
}

/* ===================== STT with simple VAD (silence guard) ===================== */
let mediaStream = null;
let mediaRecorder = null;
let audioChunks = [];

let audioCtx = null;
let analyser = null;
let sourceNode = null;
let vadRaf = 0;
let speechDetected = false;

function startVAD(stream) {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 2048;

  sourceNode = audioCtx.createMediaStreamSource(stream);
  sourceNode.connect(analyser);

  const buf = new Uint8Array(analyser.fftSize);
  speechDetected = false;

  const THRESH = 12;        
  const HITS_TO_CONFIRM = 6; 

  let hits = 0;

  const tick = () => {
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const dev = buf[i] - 128;
      sum += dev * dev;
    }
    const rms = Math.sqrt(sum / buf.length);

    if (rms > THRESH) {
      hits++;
      if (hits >= HITS_TO_CONFIRM) speechDetected = true;
    } else {
      hits = Math.max(0, hits - 1);
    }

    vadRaf = requestAnimationFrame(tick);
  };

  vadRaf = requestAnimationFrame(tick);
}

function stopVAD() {
  try { cancelAnimationFrame(vadRaf); } catch (e) {}
  vadRaf = 0;
  try { sourceNode && sourceNode.disconnect(); } catch (e) {}
  try { analyser && analyser.disconnect(); } catch (e) {}
  try { audioCtx && audioCtx.close(); } catch (e) {}
  sourceNode = null; analyser = null; audioCtx = null;
}

async function startRecording() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(mediaStream, { mimeType: "audio/webm" });

    startVAD(mediaStream);

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      stopVAD();
      if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
      }
      micBtn?.classList.remove("recording");

      if (!speechDetected) {
        console.info("No speech detected; skipping STT.");
        audioChunks = [];
        return;
      }

      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      audioChunks = [];

      const fd = new FormData();
      fd.append("audio", blob, "speech.webm");

      try {
        const resp = await fetch("/api/stt", { method: "POST", body: fd });
        const data = await resp.json();
        if (data && data.text) {
          input.value = data.text;
          input.focus();
        }
      } catch (err) {
        console.error("STT /stt error:", err);
      }
    };

    mediaRecorder.start();
    micBtn?.classList.add("recording");
  } catch (e) {
    console.error("Mic permission / recording error:", e);
    micBtn?.classList.remove("recording");
    stopVAD();
    if (mediaStream) {
      mediaStream.getTracks().forEach(t => t.stop());
      mediaStream = null;
    }
  }
}

function stopRecording() {
  try {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    } else {
      micBtn?.classList.remove("recording");
      stopVAD();
      if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
      }
    }
  } catch (e) {
    console.error("stopRecording error:", e);
    stopVAD();
  }
}

if (micBtn) {
  micBtn.addEventListener("click", () => {
    if (micBtn.classList.contains("recording")) {
      stopRecording();
    } else {
      startRecording();
    }
  });
}

/* ===================== Image helpers (update instead of duplicate) ===================== */
function normTitle(s) {
  return (s || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function findCardForTitle(messageEl, title) {
  const wanted = normTitle(title);
  const cards = messageEl.querySelectorAll(".book-card");
  for (const card of cards) {
    const h = card.querySelector(".book-title");
    if (h && normTitle(h.textContent) === wanted) return card;
  }
  return null;
}

function getOrCreateCoverImg(messageEl, title) {
  const wanted = normTitle(title);
  const card = findCardForTitle(messageEl, title) || messageEl;

  let img = card.querySelector(`img.gen-img[data-title-norm="${wanted}"]`);
  if (img) return img;

  img = document.createElement("img");
  img.className = "gen-img";
  img.setAttribute("data-title-norm", wanted);
  img.alt = "Generated cover";
  img.style.cursor = "pointer";
  img.addEventListener("click", () => img.classList.toggle("full"));
  card.appendChild(img);
  return img;
}

async function fetchImageURL(prompt, size = "1024x1024", quality = "low") {
  const r = await fetch("/api/image", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ prompt, size, quality })
  });
  if (!r.ok) return null;
  const j = await r.json().catch(() => ({}));
  return j && j.url ? j.url : null;
}

// generate (or update) a cover for a specific title in this message
async function generateOrUpdateCoverForTitle({ messageEl, title, imagePrompt }) {
  const url = await fetchImageURL(imagePrompt);
  if (url) {
    const img = getOrCreateCoverImg(messageEl, title);
    img.src = url + "?t=" + Date.now(); 
  }
}

/* ===================== Extract titles from markdown ===================== */
function extractTitlesFromMarkdown(md) {
  const titles = [];
  const lines = (md || "").split(/\r?\n/);
  for (const line of lines) {
    const m = line.match(/^\s*\*\*(.+?)\*\*\s*$/);
    if (m && m[1]) titles.push(m[1].trim());
  }
  return [...new Set(titles)];
}

/* ===================== Beautify book blocks into cards ===================== */
function beautifyBookBlocks(container) {
  if (!container) return;
  const pList = Array.from(container.querySelectorAll('p'));

  for (let i = 0; i < pList.length; i++) {
    const p = pList[i];
    if (
      p.children.length === 1 &&
      p.firstElementChild.tagName === 'STRONG' &&
      p.textContent.trim()
    ) {
      const title = p.textContent.trim();

      const card = document.createElement('div');
      card.className = 'book-card';

      const header = document.createElement('div');
      header.className = 'book-title';
      header.textContent = title;
      card.appendChild(header);

      let node = p.nextSibling;
      p.remove();

      while (node) {
        const next = node.nextSibling;
        if (
          node.nodeType === 1 &&
          node.tagName === 'P' &&
          node.children.length === 1 &&
          node.firstElementChild.tagName === 'STRONG' &&
          node.textContent.trim()
        ) break;

        card.appendChild(node);
        node = next;
      }

      if (node) container.insertBefore(card, node);
      else container.appendChild(card);

      card.querySelectorAll('p').forEach(pp => {
        const t = (pp.textContent || '').trim();
        if (/^Why this book\??$/i.test(t)) {
          pp.className = 'why-label';
          pp.textContent = 'Why this book?';
        } else if (/^Summary:?$/i.test(t)) {
          pp.className = 'summary-label';
          pp.textContent = 'Summary';
        }
      });

      card.querySelectorAll('ul').forEach(ul => ul.classList.add('book-reasons'));
    }
  }
}

/* ===================== Buttons per title (generate/update cover + single TTS) ===================== */
function addImageButtonsForTitles(messageEl, replyMarkdown) {
  if (!messageEl) return;
  const titles = extractTitlesFromMarkdown(replyMarkdown);
  if (!titles.length) return;

  const box = document.createElement('div');
  box.className = 'd-flex flex-wrap gap-2 mt-2';

  titles.forEach((title) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm btn-outline-secondary icon-btn';
    btn.title = `Generate/Update cover for "${title}"`;
    btn.innerHTML = `🖼️ <span>${title}</span>`;

    btn.onclick = async () => {
      const old = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '…';
      try {
        const promptText =
          `Design a simple, minimalist book cover for "${title}". ` +
          `Use a clean layout, readable title, and one symbolic illustration.`;

        await generateOrUpdateCoverForTitle({
        messageEl,
        title,
        imagePrompt: promptText
        });
      } finally {
        btn.disabled = false;
        btn.innerHTML = old;
      }
    };

    box.appendChild(btn);
  });

  messageEl.appendChild(box);
}

/* ===================== Chat rendering ===================== */
function addMsg(text, who) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${who === "user" ? "msg-user" : "msg-bot"}`;

  const header = `<strong>${who === "user" ? "You" : "Bot"}</strong><br>`;
  const body = who === "user"
    ? escapeHtml(text).replace(/\n/g, "<br>")
    : renderBot(text);

  wrap.innerHTML = header + body;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

addMsg("Hello! I can recommend books from our small library and include a full summary for the top pick. How can I help?", "bot");

/* ===================== Submit handler ===================== */
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = input.value.trim();
  if (!msg) return;

  addMsg(msg, "user");
  input.value = "";
  input.focus();

  sendBtn.disabled = true;
  const thinking = document.createElement("div");
  thinking.className = "p-3 rounded mb-2 msg-bot";
  thinking.innerHTML = "<strong>Bot</strong><br>…thinking…";
  chat.appendChild(thinking);
  chat.scrollTop = chat.scrollHeight;

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();
    chat.removeChild(thinking);

    const replyText = data.reply || "(no reply)";
    const el = addMsg(replyText, "bot");

    beautifyBookBlocks(el);
    addSpeakButtonToMessage(el, replyText);
    addImageButtonsForTitles(el, replyText);

    if (autoSpeakCheckbox && autoSpeakCheckbox.checked && !anyTTSPlaying()) {
      await ensureSingleTTSPlay(el, replyText);
    }
  } catch (err) {
    chat.removeChild(thinking);
    addMsg("Error contacting server.", "bot");
    console.error(err);
  } finally {
    sendBtn.disabled = false;
  }
});
