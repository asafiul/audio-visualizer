document.addEventListener('DOMContentLoaded', () => {
    const audioFile = document.getElementById('audioFile');
    const fileName = document.getElementById('fileName');
    const startBtn = document.getElementById('startBtn');
    const uploadForm = document.getElementById('uploadForm');
    const progressSection = document.getElementById('progressSection');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const resultSection = document.getElementById('resultSection');
    const downloadBtn = document.getElementById('downloadBtn');
    const newBtn = document.getElementById('newBtn');
    const errorSection = document.getElementById('errorSection');
    const errorText = document.getElementById('errorText');
    const retryBtn = document.getElementById('retryBtn');

    let currentJobId = null;

    audioFile.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            fileName.textContent = e.target.files[0].name;
            startBtn.disabled = false;
        } else {
            fileName.textContent = '';
            startBtn.disabled = true;
        }
    });

    startBtn.addEventListener('click', async () => {
        const file = audioFile.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append('audio', file);

        const res = document.getElementById('resolution').value.split('x');
        formData.append('width', res[0]);
        formData.append('height', res[1]);

        formData.append('fps', document.getElementById('fps').value);
        formData.append('spectrum_style', document.getElementById('spectrumStyle').value);
        formData.append('waveform_style', document.getElementById('waveformStyle').value);
        formData.append('primary_color', document.getElementById('primaryColor').value);
        formData.append('secondary_color', document.getElementById('secondaryColor').value);

        showSection('progress');
        updateProgress(0, 'Загрузка...');

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Ошибка загрузки');
            }

            const data = await response.json();
            currentJobId = data.job_id;
            pollProgress();

        } catch (error) {
            showError(error.message);
        }
    });

    function pollProgress() {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/status/${currentJobId}`);
                const data = await response.json();

                updateProgress(data.progress, data.message);

                if (data.status === 'completed') {
                    clearInterval(interval);
                    showSection('result');
                } else if (data.status === 'error') {
                    clearInterval(interval);
                    showError(data.message);
                }
            } catch (error) {
                clearInterval(interval);
                showError('Ошибка соединения');
            }
        }, 500);
    }

    function updateProgress(percent, message) {
        progressFill.style.width = percent + '%';
        progressText.textContent = message || `Обработка: ${percent}%`;
    }

    downloadBtn.addEventListener('click', () => {
        if (currentJobId) {
            window.location.href = `/download/${currentJobId}`;
        }
    });

    newBtn.addEventListener('click', () => {
        resetForm();
        showSection('upload');
    });

    retryBtn.addEventListener('click', () => {
        showSection('upload');
    });

    function showSection(section) {
        uploadForm.style.display = section === 'upload' ? 'block' : 'none';
        progressSection.style.display = section === 'progress' ? 'block' : 'none';
        resultSection.style.display = section === 'result' ? 'block' : 'none';
        errorSection.style.display = section === 'error' ? 'block' : 'none';
    }

    function showError(message) {
        errorText.textContent = message;
        showSection('error');
    }

    function resetForm() {
        audioFile.value = '';
        fileName.textContent = '';
        startBtn.disabled = true;
        progressFill.style.width = '0%';
        currentJobId = null;
    }
});
