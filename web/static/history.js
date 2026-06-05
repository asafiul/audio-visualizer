/**
 * History module.
 * Manages localStorage history of render runs.
 */
window.History = (function () {
    const HISTORY_KEY = 'av_history';
    const MAX_HISTORY = 20;

    function getAll() {
        try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
        catch { return []; }
    }

    function save(entry) {
        const history = getAll();
        history.unshift(entry);
        if (history.length > MAX_HISTORY) history.length = MAX_HISTORY;
        localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function render(callbacks) {
        const list = document.getElementById('historyList');
        const empty = document.getElementById('historyEmpty');
        const history = getAll();

        list.querySelectorAll('.history-item').forEach(el => el.remove());
        if (history.length === 0) { empty.style.display = ''; return; }
        empty.style.display = 'none';

        for (const entry of history) {
            const item = document.createElement('div');
            item.className = 'history-item';
            const date = new Date(entry.date);
            const timeStr = date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

            item.innerHTML =
                '<div class="history-item-name">' + escapeHtml(entry.filename) + '</div>' +
                '<div class="history-item-meta"><span>' + timeStr + '</span><span>' +
                (entry.video ? entry.video.resolution : '?') + ' · ' +
                (entry.video ? entry.video.fps : '?') + 'fps</span></div>' +
                '<div class="history-item-layers">' + (entry.order || []).join(' → ') + '</div>' +
                '<div class="history-item-actions" style="margin-top:6px;display:flex;gap:4px;">' +
                '<button class="btn btn-sm history-restore-btn">Restore Config</button>' +
                '<button class="btn btn-sm history-preview-btn">▶ Preview</button>' +
                '<button class="btn btn-sm history-download-btn">↓</button>' +
                '</div>';

            item.querySelector('.history-restore-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (callbacks.onRestore) callbacks.onRestore(entry);
            });
            item.querySelector('.history-preview-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (callbacks.onPreview && entry.id) callbacks.onPreview(entry.id);
            });
            item.querySelector('.history-download-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (entry.id) window.location.href = '/download/' + entry.id;
            });

            list.appendChild(item);
        }
    }

    return {
        getAll: getAll,
        save: save,
        render: render,
    };
})();
