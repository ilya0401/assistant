"use strict";

const WAKE_PHRASES = ["привет ассистент", "привет, ассистент", "привет асистент"];
const STOP_PHRASES  = ["конец записи", "конец записи."];
const RECORD_TIMEOUT_MS = 120_000;

let recognition           = null;
let stopRecognition       = null;
let mediaRecorder         = null;
let audioChunks           = [];
let currentState          = "init";
let recordTimer           = null;
let clarificationContext  = null;
let clarificationAttempts = 0;
let pendingEntry          = null;

function buildFullTask(raw) {
    const prefix = document.getElementById("taskPrefix").value;
    if (!raw) return prefix ? `${prefix}-?` : "?";
    if (raw.includes("-")) return raw.toUpperCase();
    return prefix ? `${prefix}-${raw}` : raw;
}

// ── TTS ───────────────────────────────────────────────────────────────────────

function pickRobotVoice() {
    const voices = speechSynthesis.getVoices();
    const ruMale = voices.find(v =>
        v.lang.startsWith("ru") && /male|мужской|dmitri|yuri|pavel/i.test(v.name)
    );
    const ruAny = voices.find(v => v.lang.startsWith("ru"));
    return ruMale ?? ruAny ?? null;
}

function speakText(text) {
    return new Promise((resolve) => {
        if (!window.speechSynthesis) { resolve(); return; }
        speechSynthesis.cancel();
        const utter  = new SpeechSynthesisUtterance(text);
        utter.lang   = "ru-RU";
        utter.rate   = 1;
        utter.pitch  = 0.55;
        utter.volume = 1;
        const voice  = pickRobotVoice();
        if (voice) utter.voice = voice;
        utter.onend   = resolve;
        utter.onerror = resolve;
        speechSynthesis.speak(utter);
    });
}

speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();

// ── UI ────────────────────────────────────────────────────────────────────────

function setState(state, message) {
    currentState = state;
    document.getElementById("pulse").className       = "pulse " + state;
    document.getElementById("stateText").textContent = message;
    document.getElementById("status").textContent    = message;

    const icons = { idle: "🐻", listening: "👂", recording: "🎙️", processing: "⏳", speaking: "🔊" };
    const el = document.getElementById("avatar");
    el.textContent = icons[state] ?? "🐻";
    el.className   = "avatar " + state;
}

function esc(str) {
    const d = document.createElement("div");
    d.textContent = str ?? "—";
    return d.innerHTML;
}

function showResult(id, transcribed, parsed, jiraStatus) {
    const jiraLabels = {
        ok:        '<span class="jira-badge jira-ok">✓ Залогировано в Jira</span>',
        not_found: '<span class="jira-badge jira-warn">⚠ Задача не найдена в Jira</span>',
        error:     '<span class="jira-badge jira-warn">⚠ Ошибка подключения к Jira</span>',
        skipped:   '',
    };
    const jiraHtml = jiraLabels[jiraStatus] ?? "";

    document.getElementById("resultPanel").style.display = "block";
    document.getElementById("resultContent").innerHTML = `
        <span class="success-badge">✓ Записано #${esc(String(id))}</span>
        ${jiraHtml}
        <div class="transcribed-text">«${esc(transcribed)}»</div>
        <div class="result-grid">
            <div class="result-item">
                <div class="label">Номер задачи</div>
                <div class="value">${esc(parsed.task)}</div>
            </div>
            <div class="result-item">
                <div class="label">Дата</div>
                <div class="value">${esc(parsed.date)}</div>
            </div>
            <div class="result-item">
                <div class="label">Время на задачу</div>
                <div class="value">${esc(parsed.time_spent)}</div>
            </div>
            <div class="result-item full">
                <div class="label">Действия по задаче</div>
                <div class="value">${esc(parsed.description)}</div>
            </div>
        </div>`;
}

function showMessage(text, type = "info") {
    document.getElementById("resultPanel").style.display = "block";
    const cls = type === "error" ? "error-msg" : "info-msg";
    document.getElementById("resultContent").innerHTML =
        `<div class="${cls}">${type === "error" ? "⚠️" : "💬"} ${text}</div>`;
}

// ── Full-form modal ───────────────────────────────────────────────────────────

function showFullFormModal(data) {
    document.getElementById("formTask").value = data.task || "";
    document.getElementById("formDate").value = data.date || "";
    document.getElementById("formTime").value = data.time_spent || "";
    document.getElementById("formDesc").value = data.description || "";
    document.getElementById("fullFormModal").style.display = "flex";
    setState("idle", "Проверь и дополни данные");
}

function hideFullFormModal() {
    document.getElementById("fullFormModal").style.display = "none";
}

async function onFullFormSubmit() {
    const task        = document.getElementById("formTask").value.trim();
    const date        = document.getElementById("formDate").value.trim();
    const time_spent  = document.getElementById("formTime").value.trim();
    const descField   = document.getElementById("formDesc");
    const description = descField.value.trim();

    if (!description) {
        descField.reportValidity();
        return;
    }

    hideFullFormModal();
    await confirmEntry({
        task,
        date,
        time_spent,
        description,
        transcribed: pendingEntry?.transcribed || "",
    });
}

async function confirmEntry(entry) {
    setState("processing", "Сохраняю...");
    let data;
    try {
        const resp = await fetch("/confirm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(entry),
        });
        data = await resp.json();
    } catch (err) {
        await speakText("Ошибка соединения с сервером.");
        returnToIdle();
        return;
    }

    setState("speaking", `Винни: «${data.voice_message}»`);
    await speakText(data.voice_message);
    showResult(data.id, data.transcribed, data.parsed, data.jira_status);
    loadEntries();
    pendingEntry = null;
    returnToIdle();
}

// ── Beep ──────────────────────────────────────────────────────────────────────

function playBeep(freq = 880, duration = 0.2) {
    try {
        const ctx  = new (window.AudioContext || window.webkitAudioContext)();
        const osc  = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + duration);
    } catch (_) {}
}

// ── Wake word ─────────────────────────────────────────────────────────────────

function startWakeWordDetection() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
        showMessage("Браузер не поддерживает Web Speech API. Используй Chrome.", "error");
        return;
    }
    recognition = new SR();
    recognition.lang = "ru-RU";
    recognition.continuous     = true;
    recognition.interimResults = true;

    recognition.onresult = (event) => {
        if (currentState !== "idle") return;
        const transcript = Array.from(event.results)
            .map(r => r[0].transcript.toLowerCase()).join(" ");
        if (WAKE_PHRASES.some(p => transcript.includes(p))) onWakeWord();
    };
    recognition.onerror = (e) => { if (e.error !== "no-speech") console.warn("SR:", e.error); };
    recognition.onend   = () => { if (currentState === "idle") recognition.start(); };
    recognition.start();
    setState("idle", "Слушаю... Скажи «Привет Ассистент»");
}

async function onWakeWord() {
    recognition?.stop();
    playBeep(880, 0.2);
    setState("listening", "Привет! Расскажи что делал...");
    await speakText("Лэтсгоушки");
    startRecording();
}

// ── Stop-phrase detection ─────────────────────────────────────────────────────

function startStopPhraseDetection() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    stopRecognition = new SR();
    stopRecognition.lang = "ru-RU";
    stopRecognition.continuous     = true;
    stopRecognition.interimResults = true;

    stopRecognition.onresult = (event) => {
        if (currentState !== "recording") return;
        const transcript = Array.from(event.results)
            .map(r => r[0].transcript.toLowerCase()).join(" ");
        if (STOP_PHRASES.some(p => transcript.includes(p))) {
            stopRecognition?.stop();
            stopRecording();
        }
    };
    stopRecognition.onerror = (e) => { if (e.error !== "no-speech") console.warn("Stop-SR:", e.error); };
    stopRecognition.onend   = () => { if (currentState === "recording") stopRecognition.start(); };
    stopRecognition.start();
}

// ── Recording ─────────────────────────────────────────────────────────────────

async function startRecording() {
    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        await speakText("Нет доступа к микрофону. Разреши использование микрофона в браузере.");
        returnToIdle();
        return;
    }

    audioChunks = [];
    const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg"]
        .find(t => MediaRecorder.isTypeSupported(t)) ?? "";

    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        document.getElementById("stopBtn").style.display = "none";
        await speakText(clarificationContext ? "Принял" : "Запись успешно создана");
        processAudio();
    };

    mediaRecorder.start(200);

    const prompt = clarificationContext
        ? "Слушаю ответ... Скажи «Конец записи» когда закончишь"
        : "Запись... Скажи «Конец записи» когда закончишь";
    setState("recording", prompt);
    document.getElementById("stopBtn").style.display = "block";

    recordTimer = setTimeout(() => {
        console.warn("Max recording time reached");
        stopRecording();
    }, RECORD_TIMEOUT_MS);

    startStopPhraseDetection();
}

function stopRecording() {
    stopRecognition?.stop();
    stopRecognition = null;
    if (recordTimer) { clearTimeout(recordTimer); recordTimer = null; }
    if (mediaRecorder?.state !== "inactive") mediaRecorder?.stop();
}

// ── Processing ────────────────────────────────────────────────────────────────

async function processAudio() {
    setState("processing", "Обрабатываю...");

    const blob = new Blob(audioChunks, { type: audioChunks[0]?.type ?? "audio/webm" });
    const form = new FormData();
    form.append("file", blob, "recording.webm");
    form.append("task_prefix", document.getElementById("taskPrefix").value);

    if (clarificationContext) {
        form.append("context", JSON.stringify(clarificationContext));
    }

    let data;
    try {
        const resp = await fetch("/process", { method: "POST", body: form });
        data = await resp.json();
    } catch (err) {
        await speakText("Ошибка соединения с сервером.");
        returnToIdle();
        return;
    }

    if (data.status === "task_confirmation") {
        const fullTask = buildFullTask(data.parsed.task);
        pendingEntry = { ...data.parsed, task: fullTask, transcribed: data.transcribed };
        clarificationAttempts = 0;
        showFullFormModal(pendingEntry);
        return;
    }

    if (data.status === "clarification") {
        clarificationContext = data.context;
        clarificationAttempts++;

        if (clarificationAttempts >= 2) {
            clarificationAttempts = 0;
            clarificationContext  = null;
            pendingEntry = { ...(data.context || {}), transcribed: "" };
            await speakText("Не смог расслышать, заполни данные вручную");
            showFullFormModal(data.context || {});
        } else {
            setState("speaking", `Винни: «${data.voice_message}»`);
            await speakText(data.voice_message);
            showMessage(data.voice_message);
            setState("listening", "Жду ответа...");
            setTimeout(() => startRecording(), 300);
        }
        return;
    }

    if (data.status === "success") {
        setState("speaking", `Винни: «${data.voice_message}»`);
        await speakText(data.voice_message);
        showResult(data.id, data.transcribed, data.parsed, data.jira_status);
        loadEntries();
        returnToIdle();
        return;
    }

    setState("speaking", `Винни: «${data.voice_message ?? "Ошибка"}»`);
    await speakText(data.voice_message ?? "Произошла ошибка");
    showMessage(data.voice_message ?? "Произошла ошибка", "error");
    returnToIdle();
}

function returnToIdle() {
    clarificationContext  = null;
    clarificationAttempts = 0;
    setState("idle", "Слушаю... Скажи «Привет Ассистент»");
    startWakeWordDetection();
}

// ── Entries ───────────────────────────────────────────────────────────────────

async function loadEntries() {
    try {
        const resp    = await fetch("/entries");
        const entries = await resp.json();
        const list    = document.getElementById("entriesList");
        if (!entries.length) {
            list.innerHTML = "<p class='empty'>Записей пока нет</p>";
            return;
        }
        list.innerHTML = entries.map(e => `
            <div class="entry-card">
                <span class="entry-task">${esc(e.task)}</span>
                <span class="entry-meta">${esc(e.date)} · ${esc(e.time_spent)}</span>
                <span class="entry-desc">${esc(e.description)}</span>
            </div>`).join("");
    } catch (_) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.getElementById("stopBtn").addEventListener("click", stopRecording);
loadEntries();
startWakeWordDetection();
