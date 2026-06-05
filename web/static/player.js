/**
 * Audio Player & Trim module.
 * Manages custom audio player, playback, and trim handles.
 */
window.Player = (function () {
    let audioDuration = 0;
    let trimStart = 0;
    let trimEnd = 0;
    let isPlaying = false;
    let animFrame = null;
    let trimPlayInterval = null;
    let draggingHandle = null;
    let hasAudio = false;

    // DOM refs (resolved lazily)
    const $ = (id) => document.getElementById(id);

    function el() {
        return {
            audioPlayer: $('audioPlayer'),
            playPauseBtn: $('playPauseBtn'),
            playIcon: $('playIcon'),
            playerTime: $('playerTime'),
            playerDuration: $('playerDuration'),
            playerTrack: $('playerTrack'),
            playerTrimRegion: $('playerTrimRegion'),
            playerProgress: $('playerProgress'),
            playerCursor: $('playerCursor'),
            handleStart: $('handleStart'),
            handleEnd: $('handleEnd'),
            trimStartInput: $('trimStart'),
            trimEndInput: $('trimEnd'),
            trimStartDec: $('trimStartDec'),
            trimStartInc: $('trimStartInc'),
            trimEndDec: $('trimEndDec'),
            trimEndInc: $('trimEndInc'),
            trimPlayBtn: $('trimPlayBtn'),
            trimInfoEl: $('trimInfo'),
        };
    }

    function fmtTime(sec) {
        if (!isFinite(sec) || sec < 0) sec = 0;
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return m + ':' + s.toString().padStart(2, '0');
    }

    function updatePlayerUI() {
        const e = el();
        if (audioDuration <= 0) return;
        const startPct = (trimStart / audioDuration) * 100;
        const endPct = (trimEnd / audioDuration) * 100;
        e.playerTrimRegion.style.left = startPct + '%';
        e.playerTrimRegion.style.width = (endPct - startPct) + '%';
        e.handleStart.style.left = 'calc(' + startPct + '% - 6px)';
        e.handleEnd.style.left = 'calc(' + endPct + '% - 6px)';
        const selectedDur = Math.max(0, trimEnd - trimStart);
        e.trimInfoEl.textContent = fmtTime(trimStart) + ' – ' + fmtTime(trimEnd) + '  (' + selectedDur.toFixed(1) + 's)';
    }

    function updateCursor() {
        const e = el();
        if (audioDuration <= 0) return;
        const ct = e.audioPlayer.currentTime;
        const pct = (ct / audioDuration) * 100;
        e.playerCursor.style.left = pct + '%';
        e.playerProgress.style.width = pct + '%';
        e.playerTime.textContent = fmtTime(ct);
    }

    function animLoop() {
        updateCursor();
        if (isPlaying) animFrame = requestAnimationFrame(animLoop);
    }

    function stopAudio() {
        const e = el();
        e.audioPlayer.pause();
        isPlaying = false;
        e.playIcon.textContent = '▶';
        if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null; }
        if (trimPlayInterval) { clearInterval(trimPlayInterval); trimPlayInterval = null; }
        updateCursor();
    }

    function resetUI() {
        const e = el();
        stopAudio();
        e.playerTime.textContent = fmtTime(0);
        e.playerDuration.textContent = fmtTime(0);
        e.playerProgress.style.width = '0%';
        e.playerCursor.style.left = '0%';
        e.playerTrimRegion.style.left = '0%';
        e.playerTrimRegion.style.width = '100%';
        e.handleStart.style.left = 'calc(0% - 6px)';
        e.handleEnd.style.left = 'calc(100% - 6px)';
        e.trimStartInput.value = '0.0';
        e.trimEndInput.value = '0.0';
        e.trimInfoEl.textContent = 'Upload audio to trim';
        hasAudio = false;
        audioDuration = 0; trimStart = 0; trimEnd = 0;
    }

    function setTrimStart(val) {
        trimStart = Math.max(0, Math.min(val, trimEnd - 0.1));
        el().trimStartInput.value = trimStart.toFixed(1);
        updatePlayerUI();
    }

    function setTrimEnd(val) {
        trimEnd = Math.max(trimStart + 0.1, Math.min(val, audioDuration));
        el().trimEndInput.value = trimEnd.toFixed(1);
        updatePlayerUI();
    }

    function loadAudio(url, pendingTrimOpts) {
        const e = el();
        stopAudio();
        e.audioPlayer.src = url;
        e.audioPlayer.addEventListener('loadedmetadata', () => {
            audioDuration = e.audioPlayer.duration;
            trimStart = 0; trimEnd = audioDuration;
            e.trimStartInput.max = audioDuration;
            e.trimEndInput.max = audioDuration;

            // Apply pending trim if provided
            if (pendingTrimOpts && pendingTrimOpts.start != null && pendingTrimOpts.end != null) {
                setTrimStart(pendingTrimOpts.start);
                setTrimEnd(pendingTrimOpts.end);
            } else {
                e.trimStartInput.value = '0.0';
                e.trimEndInput.value = audioDuration.toFixed(1);
            }

            e.playerDuration.textContent = fmtTime(audioDuration);
            e.playerTime.textContent = fmtTime(0);
            hasAudio = true;
            updatePlayerUI();
        }, { once: true });
    }

    function unloadAudio() {
        const e = el();
        stopAudio();
        e.audioPlayer.src = '';
        hasAudio = false;
        resetUI();
    }

    function init() {
        const e = el();

        // Play / Pause
        e.playPauseBtn.addEventListener('click', () => {
            if (!hasAudio) return;
            if (isPlaying) {
                stopAudio();
            } else {
                e.audioPlayer.play();
                isPlaying = true;
                e.playIcon.textContent = '⏸';
                animFrame = requestAnimationFrame(animLoop);
            }
        });

        e.audioPlayer.addEventListener('ended', stopAudio);

        // Click on track to seek
        e.playerTrack.addEventListener('click', (ev) => {
            if (!hasAudio) return;
            if (ev.target.closest('.player-handle')) return;
            const rect = e.playerTrack.getBoundingClientRect();
            const pct = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
            e.audioPlayer.currentTime = pct * audioDuration;
            updateCursor();
        });

        // Draggable handles
        function onHandleMouseDown(handle, ev) {
            if (!hasAudio) return;
            ev.preventDefault(); ev.stopPropagation();
            draggingHandle = handle;
            handle.classList.add('dragging');
            document.addEventListener('mousemove', onHandleMouseMove);
            document.addEventListener('mouseup', onHandleMouseUp);
        }

        e.handleStart.addEventListener('mousedown', (ev) => onHandleMouseDown(e.handleStart, ev));
        e.handleEnd.addEventListener('mousedown', (ev) => onHandleMouseDown(e.handleEnd, ev));

        function onHandleMouseMove(ev) {
            if (!draggingHandle) return;
            const rect = e.playerTrack.getBoundingClientRect();
            const pct = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
            const time = pct * audioDuration;
            if (draggingHandle === e.handleStart) setTrimStart(time);
            else setTrimEnd(time);
        }

        function onHandleMouseUp() {
            if (draggingHandle) draggingHandle.classList.remove('dragging');
            draggingHandle = null;
            document.removeEventListener('mousemove', onHandleMouseMove);
            document.removeEventListener('mouseup', onHandleMouseUp);
        }

        // Touch support
        e.handleStart.addEventListener('touchstart', (ev) => { if (!hasAudio) return; ev.preventDefault(); draggingHandle = e.handleStart; e.handleStart.classList.add('dragging'); }, { passive: false });
        e.handleEnd.addEventListener('touchstart', (ev) => { if (!hasAudio) return; ev.preventDefault(); draggingHandle = e.handleEnd; e.handleEnd.classList.add('dragging'); }, { passive: false });

        document.addEventListener('touchmove', (ev) => {
            if (!draggingHandle) return;
            const touch = ev.touches[0];
            const rect = e.playerTrack.getBoundingClientRect();
            const pct = Math.max(0, Math.min(1, (touch.clientX - rect.left) / rect.width));
            const time = pct * audioDuration;
            if (draggingHandle === e.handleStart) setTrimStart(time);
            else setTrimEnd(time);
        }, { passive: false });

        document.addEventListener('touchend', () => {
            if (draggingHandle) draggingHandle.classList.remove('dragging');
            draggingHandle = null;
        });

        // Trim inputs
        e.trimStartInput.addEventListener('change', () => setTrimStart(parseFloat(e.trimStartInput.value) || 0));
        e.trimEndInput.addEventListener('change', () => setTrimEnd(parseFloat(e.trimEndInput.value) || audioDuration));
        e.trimStartDec.addEventListener('click', () => setTrimStart(trimStart - 0.5));
        e.trimStartInc.addEventListener('click', () => setTrimStart(trimStart + 0.5));
        e.trimEndDec.addEventListener('click', () => setTrimEnd(trimEnd - 0.5));
        e.trimEndInc.addEventListener('click', () => setTrimEnd(trimEnd + 0.5));

        // Play trimmed selection
        e.trimPlayBtn.addEventListener('click', () => {
            if (!hasAudio) return;
            e.audioPlayer.currentTime = trimStart;
            e.audioPlayer.play();
            isPlaying = true;
            e.playIcon.textContent = '⏸';
            animFrame = requestAnimationFrame(animLoop);
            if (trimPlayInterval) clearInterval(trimPlayInterval);
            trimPlayInterval = setInterval(() => {
                if (e.audioPlayer.currentTime >= trimEnd) {
                    stopAudio();
                }
            }, 50);
        });

        resetUI();
    }

    // Public API
    return {
        init: init,
        loadAudio: loadAudio,
        unloadAudio: unloadAudio,
        stopAudio: stopAudio,
        resetUI: resetUI,
        setInfoText: function (text) { el().trimInfoEl.textContent = text; },
        getTrim: function () { return { start: trimStart, end: trimEnd, duration: audioDuration }; },
        hasTrim: function () {
            return audioDuration > 0 && (trimStart > 0.05 || trimEnd < audioDuration - 0.05);
        },
        hasAudioLoaded: function () { return hasAudio; },
    };
})();
