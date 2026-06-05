/**
 * Main App orchestrator.
 * Wires together Player, Pipeline, and History modules.
 */
document.addEventListener('DOMContentLoaded', () => {
    const $ = (id) => document.getElementById(id);
    let currentJobId = null;
    let restoredJobId = null;  // job_id whose audio we can reuse

    // ── DOM refs ──
    const headerHome    = $('headerHome');
    const audioFile     = $('audioFile');
    const uploadArea    = $('uploadArea');
    const fileName      = $('fileName');
    const renderBtn     = $('renderBtn');
    const progressOverlay = $('progressOverlay');
    const progressFill  = $('progressFill');
    const progressText  = $('progressText');
    const progressTitle = $('progressTitle');
    const progressActions = $('progressActions');
    const progressError = $('progressError');
    const previewResultBtn  = $('previewResultBtn');
    const downloadResultBtn = $('downloadResultBtn');
    const closeResultBtn    = $('closeResultBtn');
    const previewOverlay    = $('previewOverlay');
    const previewVideo      = $('previewVideo');
    const previewDownloadBtn = $('previewDownloadBtn');
    const previewCloseBtn   = $('previewCloseBtn');

    // ── Init ──
    async function init() {
        try {
            const resp = await fetch('/api/layers');
            const data = await resp.json();
            const colors = data.color_defaults || {};
            if (colors.primary) $('primaryColor').value = Pipeline.rgbToHex(colors.primary);
            if (colors.secondary) $('secondaryColor').value = Pipeline.rgbToHex(colors.secondary);

            Pipeline.init(data.layers, data.default_order);
            Player.init();
            History.render({ onRestore: restoreFromHistory, onPreview: showPreview });
        } catch (e) {
            console.error('Failed to load layer metadata:', e);
        }
    }

    // ── Render button state ──
    function updateRenderBtn() {
        const hasAudio = audioFile.files.length > 0 || restoredJobId;
        renderBtn.disabled = !(hasAudio && Pipeline.getCount() > 0);
    }

    // Expose for Pipeline module
    window.App = { updateRenderBtn: updateRenderBtn };

    // ── Header Home ──
    headerHome.addEventListener('click', (e) => { e.preventDefault(); resetToMain(); });

    function resetToMain() {
        closePreview();
        progressOverlay.classList.remove('visible');
        Pipeline.resetToDefaults();
        audioFile.value = '';
        fileName.textContent = '';
        uploadArea.classList.remove('has-file');
        Player.unloadAudio();
        $('resolution').value = '1920x1080';
        $('fps').value = '30';
        currentJobId = null;
        restoredJobId = null;
        updateRenderBtn();
    }

    // ── Upload Area ──
    uploadArea.addEventListener('click', () => audioFile.click());
    uploadArea.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.style.borderColor = 'var(--accent)'; });
    uploadArea.addEventListener('dragleave', () => { uploadArea.style.borderColor = ''; });
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault(); uploadArea.style.borderColor = '';
        if (e.dataTransfer.files.length > 0) { audioFile.files = e.dataTransfer.files; onFileSelected(); }
    });
    audioFile.addEventListener('change', onFileSelected);

    function onFileSelected() {
        restoredJobId = null;  // user picked a new file, clear reuse
        if (audioFile.files.length > 0) {
            const file = audioFile.files[0];
            fileName.textContent = file.name;
            uploadArea.classList.add('has-file');
            Player.loadAudio(URL.createObjectURL(file));
            updateRenderBtn();
        } else {
            fileName.textContent = '';
            uploadArea.classList.remove('has-file');
            Player.unloadAudio();
            updateRenderBtn();
        }
    }

    // ── Preview Overlay ──
    function showPreview(jobId) {
        previewOverlay.classList.add('visible');
        previewVideo.src = '/preview/' + jobId;
        previewVideo.load();
        previewDownloadBtn.onclick = () => { window.location.href = '/download/' + jobId; };
    }

    function closePreview() {
        previewOverlay.classList.remove('visible');
        previewVideo.pause();
        previewVideo.src = '';
    }

    previewCloseBtn.addEventListener('click', closePreview);
    previewOverlay.addEventListener('click', (e) => { if (e.target === previewOverlay) closePreview(); });

    // ── Render / Submit ──
    renderBtn.addEventListener('click', startRender);

    async function startRender() {
        const file = audioFile.files[0];
        const hasNewFile = !!file;
        const hasReuse = !!restoredJobId;
        if ((!hasNewFile && !hasReuse) || Pipeline.getCount() === 0) return;

        const res = $('resolution').value.split('x');
        const fps = $('fps').value;
        const pipelineConfig = {
            video: { width: parseInt(res[0]), height: parseInt(res[1]), fps: parseInt(fps) },
            colors: { primary: $('primaryColor').value, secondary: $('secondaryColor').value },
            order: Pipeline.getOrder(),
            layer_params: Pipeline.getLayerParams(),
        };

        if (Player.hasTrim()) {
            const t = Player.getTrim();
            pipelineConfig.trim = { start: t.start, end: t.end };
        }

        const formData = new FormData();
        if (hasNewFile) {
            formData.append('audio', file);
        } else {
            formData.append('reuse_audio_job_id', restoredJobId);
        }
        formData.append('pipeline_config', JSON.stringify(pipelineConfig));

        Player.stopAudio();
        showProgress();

        try {
            const resp = await fetch('/upload', { method: 'POST', body: formData });
            if (!resp.ok) { const err = await resp.json(); throw new Error(err.error || 'Upload failed'); }
            const data = await resp.json();
            currentJobId = data.job_id;
            pollProgress();
        } catch (e) {
            showProgressError(e.message);
        }
    }

    // ── Progress ──
    function showProgress() {
        progressOverlay.classList.add('visible');
        progressTitle.textContent = 'Rendering...';
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
        progressActions.style.display = 'none';
        progressError.style.display = 'none';
    }

    function showProgressError(msg) {
        progressTitle.textContent = 'Error';
        progressError.textContent = msg;
        progressError.style.display = 'block';
        progressActions.style.display = 'flex';
        previewResultBtn.style.display = 'none';
        downloadResultBtn.style.display = 'none';
        closeResultBtn.textContent = 'Close';
    }

    function pollProgress() {
        const interval = setInterval(async () => {
            try {
                const resp = await fetch('/status/' + currentJobId);
                const data = await resp.json();
                progressFill.style.width = data.progress + '%';
                progressText.textContent = data.message || (data.progress + '%');

                if (data.status === 'completed') {
                    clearInterval(interval);
                    progressTitle.textContent = 'Done!';
                    progressActions.style.display = 'flex';
                    previewResultBtn.style.display = '';
                    downloadResultBtn.style.display = '';
                    closeResultBtn.textContent = 'Close';
                    saveToHistory();
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    showProgressError(data.message);
                }
            } catch (e) {
                clearInterval(interval);
                showProgressError('Connection lost');
            }
        }, 500);
    }

    previewResultBtn.addEventListener('click', () => {
        progressOverlay.classList.remove('visible');
        if (currentJobId) showPreview(currentJobId);
    });
    downloadResultBtn.addEventListener('click', () => {
        if (currentJobId) window.location.href = '/download/' + currentJobId;
    });
    closeResultBtn.addEventListener('click', () => {
        progressOverlay.classList.remove('visible');
        currentJobId = null;
    });

    // ── History integration ──
    function saveToHistory() {
        const file = audioFile.files[0];
        const trim = Player.getTrim();
        const entry = {
            id: currentJobId,
            filename: file ? file.name : (fileName.textContent || 'unknown'),
            date: new Date().toISOString(),
            order: Pipeline.getOrder(),
            layer_params: Pipeline.getLayerParams(),
            video: { resolution: $('resolution').value, fps: $('fps').value },
            colors: { primary: $('primaryColor').value, secondary: $('secondaryColor').value },
            trim: { start: trim.start, end: trim.end },
        };
        History.save(entry);
        History.render({ onRestore: restoreFromHistory, onPreview: showPreview });
    }

    function restoreFromHistory(entry) {
        // Restore pipeline
        if (entry.order && entry.layer_params) {
            Pipeline.setPipeline(entry.order, entry.layer_params);
        }

        // Restore video settings
        if (entry.video) {
            const resSelect = $('resolution');
            for (const opt of resSelect.options) {
                if (opt.value === entry.video.resolution) { opt.selected = true; break; }
            }
            const fpsSelect = $('fps');
            for (const opt of fpsSelect.options) {
                if (opt.value === entry.video.fps) { opt.selected = true; break; }
            }
        }

        // Restore colors
        if (entry.colors) {
            if (entry.colors.primary) $('primaryColor').value = entry.colors.primary;
            if (entry.colors.secondary) $('secondaryColor').value = entry.colors.secondary;
        }

        // Show filename
        fileName.textContent = entry.filename;
        uploadArea.classList.add('has-file');

        // Load audio from server if job_id is available
        restoredJobId = entry.id || null;
        if (restoredJobId) {
            const trimOpts = entry.trim || null;
            Player.loadAudio('/audio/' + restoredJobId, trimOpts);
            Player.setInfoText('Audio restored from previous run');
        } else {
            Player.unloadAudio();
            Player.setInfoText('Config restored — select audio file to continue');
        }

        updateRenderBtn();
        $('mainPanel').scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── Start ──
    init();
});
