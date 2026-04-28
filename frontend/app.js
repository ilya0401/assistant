"use strict";

const WAKE_PHRASES = ["привет ассистент", "привет, ассистент", "привет асистент"];
const STOP_PHRASES  = ["конец записи", "конец записи."];
const RECORD_TIMEOUT_MS = 120_000;

let recognition     = null;
let stopRecognition = null;
let mediaRecorder   = null;
let audioChunks     = [];
let currentState    = "init";
let recordTimer     = null;
let clarificationContext = null;

// ── TTS (браузерный, без сервера) ─────────────────────────────────────────────

function pickRobotVoice() {
    const voices = speechSynthesis.getVoices();
    // Предпочитаем русский мужской голос — звучит роботообразнее
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
        utter.rate   = 1;   // чуть быстрее — роботы говорят без пауз
        utter.pitch  = 0.55;   // низкий тон — главный маркер робота
        utter.volume = 1;
        const voice  = pickRobotVoice();
        if (voice) utter.voice = voice;
        utter.onend   = resolve;
        utter.onerror = resolve;
        speechSynthesis.speak(utter);
    });
}

// Голоса грузятся асинхронно — прогреваем список при старте
speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();

// ── UI ────────────────────────────────────────────────────────────────────────

function setState(state, message) {
    currentState = state;
    document.getElementById("pulse").className    = "pulse " + state;
    document.getElementById("stateText").textContent = message;
    document.getElementById("status").textContent    = message;

    const icons = { idle: "🐻", listening: "👂", recording: "🎙️", processing: "⏳", speaking: "🔊" };
    const el = document.getElementById("avatar");
    el.textContent = icons[state] ?? "🐻";
    el.className   = "avatar " + state;
}

function showResult(id, transcribed, parsed) {
    document.getElementById("resultPanel").style.display = "block";
    document.getElementById("resultContent").innerHTML = `
        <span class="success-badge">✓ Записано #${id}</span>
        <div class="transcribed-text">«${transcribed}»</div>
        <div class="result-grid">
            <div class="result-item">
                <div class="label">Номер задачи</div>
                <div class="value">${parsed.task ?? "—"}</div>
            </div>
            <div class="result-item">
                <div class="label">Дата</div>
                <div class="value">${parsed.date ?? "—"}</div>
            </div>
            <div class="result-item">
                <div class="label">Время на задачу</div>
                <div class="value">${parsed.time_spent ?? "—"}</div>
            </div>
            <div class="result-item full">
                <div class="label">Действия по задаче</div>
                <div class="value">${parsed.description ?? "—"}</div>
            </div>
        </div>`;
}

function showMessage(text, type = "info") {
    document.getElementById("resultPanel").style.display = "block";
    const cls = type === "error" ? "error-msg" : "info-msg";
    document.getElementById("resultContent").innerHTML =
        `<div class="${cls}">${type === "error" ? "⚠️" : "💬"} ${text}</div>`;
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
    recognition.continuous    = true;
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

// ── Stop-phrase detection (во время записи) ───────────────────────────────────

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
        await speakText("Запись успешно создана");
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
    const wasClarification = !!clarificationContext;
    if (clarificationContext) form.append("context", JSON.stringify(clarificationContext));

    let data;
    try {
        const resp = await fetch("/process", { method: "POST", body: form });
        data = await resp.json();
    } catch (err) {
        await speakText("Ошибка соединения с сервером.");
        returnToIdle();
        return;
    }

    const textToSpeak = (wasClarification && data.status === "success")
        ? "Уточнения успешно записаны"
        : data.voice_message;

    setState("speaking", `Винни: «${textToSpeak}»`);
    await speakText(textToSpeak);

    if (data.status === "success") {
        showResult(data.id, data.transcribed, data.parsed);
        loadEntries();
        returnToIdle();

    } else if (data.status === "clarification") {
        clarificationContext = data.context;
        showMessage(data.voice_message);
        setState("listening", "Жду ответа...");
        setTimeout(() => startRecording(), 300);

    } else {
        showMessage(data.voice_message ?? "Произошла ошибка", "error");
        returnToIdle();
    }
}

function returnToIdle() {
    clarificationContext = null;
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
                <span class="entry-task">${e.task}</span>
                <span class="entry-meta">${e.date} · ${e.time_spent}</span>
                <span class="entry-desc">${e.description}</span>
            </div>`).join("");
    } catch (_) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.getElementById("stopBtn").addEventListener("click", stopRecording);
loadEntries();
startWakeWordDetection();
