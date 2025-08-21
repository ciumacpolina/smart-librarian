// static/js/app.js

const form  = document.getElementById("form");
const input = document.getElementById("input");
const chat  = document.getElementById("chat");
const sendBtn = document.getElementById("send");
const autoSpeakCheckbox = document.getElementById("autoSpeak");
const micBtn = document.getElementById("micBtn");

// ===== Markdown safe options =====
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

// ===================== TTS: single-player, toggle, no overlap =====================
const ttsPlayers = new Map(); // btn -> { audio, state, url, lastTime }

async function fetchTTSBlob(text) {
  const clean = (text || "")
    .replace(/\*\*/g, "")
    .replace(/`+/g, "")
    .replace(/_/g, "");
  if (!clean.trim()) return null;

  const resp = await fetch('/tts', {
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

function addSpeakButtonToMessage(messageEl, text) {
  if (!messageEl) return;
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

// ===================== Speech-to-Text (STT) =====================
let mediaStream = null;
let mediaRecorder = null;
let audioChunks = [];

async function startRecording() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(mediaStream, { mimeType: "audio/webm" });

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      audioChunks = [];

      const fd = new FormData();
      fd.append("audio", blob, "speech.webm");

      try {
        const resp = await fetch("/stt", { method: "POST", body: fd });
        const data = await resp.json();
        if (data && data.text) {
          input.value = data.text;
          input.focus();
        }
      } catch (err) {
        console.error("STT /stt error:", err);
      } finally {
        if (mediaStream) {
          mediaStream.getTracks().forEach(t => t.stop());
          mediaStream = null;
        }
        micBtn?.classList.remove("recording");
      }
    };

    mediaRecorder.start();
    micBtn?.classList.add("recording");
  } catch (e) {
    console.error("Mic permission / recording error:", e);
    micBtn?.classList.remove("recording");
  }
}

function stopRecording() {
  try {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    } else {
      micBtn?.classList.remove("recording");
      if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
      }
    }
  } catch (e) {
    console.error("stopRecording error:", e);
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

// ===================== Image generation =====================
async function generateImageFromText(text, hostEl) {
  try {
    const resp = await fetch('/image', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ prompt: text, size: '1024x1024', quality: 'low' })
    });
    if (!resp.ok) {
      console.warn('Image generation failed:', await resp.text());
      return;
    }
    const data = await resp.json();
    if (!data.url) return;

    const img = document.createElement('img');
    img.src = data.url + '?t=' + Date.now();
    img.alt = 'Generated illustration';
    img.className = 'gen-img';
    hostEl.appendChild(img);

    // zoom la click
    img.addEventListener('click', () => img.classList.toggle('full'));
  } catch (e) {
    console.error('Image error', e);
  }
}

// — găsește titlurile în markdown ca linii de forma **Title**
function extractTitlesFromMarkdown(md) {
  const titles = [];
  const lines = (md || "").split(/\r?\n/);
  for (const line of lines) {
    const m = line.match(/^\s*\*\*(.+?)\*\*\s*$/);
    if (m && m[1]) titles.push(m[1].trim());
  }
  return [...new Set(titles)];
}

// Împachetează secțiunile începute cu **Title** într-un "card" frumos
function beautifyBookBlocks(container) {
  if (!container) return;
  const pList = Array.from(container.querySelectorAll('p'));

  for (let i = 0; i < pList.length; i++) {
    const p = pList[i];
    // paragrafe care conțin DOAR <strong>Title</strong>
    if (
      p.children.length === 1 &&
      p.firstElementChild.tagName === 'STRONG' &&
      p.textContent.trim()
    ) {
      const title = p.textContent.trim();

      // card
      const card = document.createElement('div');
      card.className = 'book-card';

      const header = document.createElement('div');
      header.className = 'book-title';
      header.textContent = title;
      card.appendChild(header);

      // mutăm în card toate nodurile până la următorul titlu
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

      // etichete
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

// — Creează un grup de butoane (🖼️ + numele cărții), unul pentru fiecare titlu
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
    btn.title = `Generate image for "${title}"`;
    btn.innerHTML = `🖼️ <span>${title}</span>`;

    btn.onclick = async () => {
      const old = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '…';
      try {
        const promptText = `Design a simple, minimalist book cover for the novel "${title}".
Use clean layout, big readable title text, and one symbolic illustration.`;
        await generateImageFromText(promptText, messageEl);
      } finally {
        btn.disabled = false;
        btn.innerHTML = old;
      }
    };

    box.appendChild(btn);
  });

  messageEl.appendChild(box);
}

// ============ Chat rendering ============
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
// după ce selectezi #chat:
addMsg("Hello! I can recommend books from our small library and include a full summary for the top pick. How can I help?", "bot");


// ============ Submit handler ============
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

    // transformăm blocurile în carduri
    beautifyBookBlocks(el);

    // TTS
    addSpeakButtonToMessage(el, replyText);

    // butoane imagine (unul per titlu)
    addImageButtonsForTitles(el, replyText);

    // auto-speak
    if (autoSpeakCheckbox && autoSpeakCheckbox.checked) {
      const fakeBtn = document.createElement('button');
      attachTTS(fakeBtn, replyText);
      fakeBtn.click();
    }
  } catch (err) {
    chat.removeChild(thinking);
    addMsg("Error contacting server.", "bot");
    console.error(err);
  } finally {
    sendBtn.disabled = false;
  }
});
