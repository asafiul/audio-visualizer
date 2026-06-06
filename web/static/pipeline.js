/**
 * Pipeline Builder module.
 * Manages layer list, add/remove/reorder, and parameter editing.
 */
window.Pipeline = (function () {
    let layersMeta = {};
    let defaultOrder = [];
    let pipeline = [];
    let activeLayerIdx = -1;
    let dragSrcIdx = null;

    const $ = (id) => document.getElementById(id);

    function rgbToHex(rgb) {
        if (!Array.isArray(rgb) || rgb.length < 3) return '#6366f1';
        return '#' + rgb.map(c => Math.max(0, Math.min(255, Math.round(c))).toString(16).padStart(2, '0')).join('');
    }

    function hexToRgb(hex) {
        hex = hex.replace('#', '');
        return [parseInt(hex.substring(0, 2), 16), parseInt(hex.substring(2, 4), 16), parseInt(hex.substring(4, 6), 16)];
    }

    function createParamLabel(key, description) {
        const label = document.createElement('label');
        label.className = 'param-label';
        label.appendChild(document.createTextNode(key));
        if (description) {
            const help = document.createElement('span');
            help.className = 'param-help';
            help.textContent = '?';
            help.setAttribute('data-tooltip', description);
            help.setAttribute('tabindex', '0');
            help.setAttribute('aria-label', description);
            label.appendChild(help);
        }
        return label;
    }

    function getDefaultParams(layerName) {
        const meta = layersMeta[layerName];
        if (!meta) return {};
        const params = {};
        for (const [key, info] of Object.entries(meta.params)) params[key] = info.default;
        return params;
    }

    function renderPipeline() {
        const pipelineList = $('pipelineList');
        const layerCount = $('layerCount');
        pipelineList.innerHTML = '';
        layerCount.textContent = pipeline.length + ' layer' + (pipeline.length !== 1 ? 's' : '');

        pipeline.forEach((layer, idx) => {
            const item = document.createElement('div');
            item.className = 'pipeline-item' + (idx === activeLayerIdx ? ' active' : '');
            item.draggable = true;
            const meta = layersMeta[layer.name] || {};
            const label = meta.label || layer.name;

            item.innerHTML = '<span class="drag-handle" title="Drag to reorder">⠿</span>' +
                '<span class="pipeline-item-index">' + (idx + 1) + '</span>' +
                '<span class="pipeline-item-name">' + label + '</span>' +
                '<button class="btn btn-icon btn-ghost remove-btn" title="Remove">×</button>';

            item.addEventListener('click', (e) => {
                if (e.target.closest('.remove-btn') || e.target.closest('.drag-handle')) return;
                selectLayer(idx);
            });
            item.querySelector('.remove-btn').addEventListener('click', (e) => { e.stopPropagation(); removeLayer(idx); });

            // Drag
            item.addEventListener('dragstart', (e) => { dragSrcIdx = idx; item.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; });
            item.addEventListener('dragend', () => { item.classList.remove('dragging'); document.querySelectorAll('.pipeline-item').forEach(el => el.classList.remove('drag-over')); dragSrcIdx = null; });
            item.addEventListener('dragover', (e) => { e.preventDefault(); if (dragSrcIdx !== null && dragSrcIdx !== idx) item.classList.add('drag-over'); });
            item.addEventListener('dragleave', () => { item.classList.remove('drag-over'); });
            item.addEventListener('drop', (e) => { e.preventDefault(); item.classList.remove('drag-over'); if (dragSrcIdx !== null && dragSrcIdx !== idx) reorderLayer(dragSrcIdx, idx); });

            pipelineList.appendChild(item);
        });

        renderAddLayerMenu();
        if (typeof window.App !== 'undefined' && window.App.updateRenderBtn) window.App.updateRenderBtn();
    }

    function selectLayer(idx) {
        if (activeLayerIdx === idx) {
            // Toggle: close if already open
            activeLayerIdx = -1;
            $('paramsPanel').style.display = 'none';
            renderPipeline();
        } else {
            activeLayerIdx = idx;
            renderPipeline();
            renderParamsPanel();
        }
    }

    function removeLayer(idx) {
        pipeline.splice(idx, 1);
        if (activeLayerIdx === idx) { activeLayerIdx = -1; $('paramsPanel').style.display = 'none'; }
        else if (activeLayerIdx > idx) activeLayerIdx--;
        renderPipeline();
    }

    function reorderLayer(fromIdx, toIdx) {
        const [moved] = pipeline.splice(fromIdx, 1);
        pipeline.splice(toIdx, 0, moved);
        if (activeLayerIdx === fromIdx) activeLayerIdx = toIdx;
        else if (activeLayerIdx > fromIdx && activeLayerIdx <= toIdx) activeLayerIdx--;
        else if (activeLayerIdx < fromIdx && activeLayerIdx >= toIdx) activeLayerIdx++;
        renderPipeline();
    }

    function renderAddLayerMenu() {
        const menu = $('addLayerMenu');
        menu.innerHTML = '';
        const usedNames = new Set(pipeline.map(l => l.name));
        for (const [name, meta] of Object.entries(layersMeta)) {
            const opt = document.createElement('div');
            const isUsed = usedNames.has(name);
            opt.className = 'add-layer-option' + (isUsed ? ' disabled' : '');
            opt.innerHTML = '<span>' + meta.label + '</span>' + (isUsed ? '<span class="already-added">added</span>' : '');
            if (!isUsed) opt.addEventListener('click', (e) => { e.stopPropagation(); addLayer(name); menu.classList.remove('open'); });
            menu.appendChild(opt);
        }
    }

    function addLayer(name) {
        pipeline.push({ name, params: getDefaultParams(name) });
        activeLayerIdx = pipeline.length - 1;
        renderPipeline(); renderParamsPanel();
    }

    function sortParamEntries(entries) {
        // Sort order: colors first, then enums/multi_enum, then booleans, then numeric/other
        const typeOrder = { 'color': 0, 'enum': 1, 'multi_enum': 1, 'boolean': 2, 'float': 3, 'integer': 3, 'string': 4, 'unknown': 5 };
        return entries.slice().sort((a, b) => {
            const orderA = typeOrder[a[1].type] !== undefined ? typeOrder[a[1].type] : 5;
            const orderB = typeOrder[b[1].type] !== undefined ? typeOrder[b[1].type] : 5;
            return orderA - orderB;
        });
    }

    function renderParamsPanel() {
        const panel = $('paramsPanel');
        const content = $('paramsContent');
        const title = $('paramsPanelTitle');

        if (activeLayerIdx < 0 || activeLayerIdx >= pipeline.length) { panel.style.display = 'none'; return; }
        panel.style.display = 'block';
        const layer = pipeline[activeLayerIdx];
        const meta = layersMeta[layer.name];
        if (!meta) { content.innerHTML = '<p style="color:var(--text-muted);font-size:12px;">No parameters</p>'; return; }

        title.textContent = meta.label + ' Settings';
        content.innerHTML = '';
        const entries = sortParamEntries(Object.entries(meta.params));
        if (entries.length === 0) { content.innerHTML = '<p style="color:var(--text-muted);font-size:12px;">No configurable parameters</p>'; return; }

        for (const [key, info] of entries) {
            const val = layer.params[key] !== undefined ? layer.params[key] : info.default;
            const group = document.createElement('div');
            group.className = 'param-group';

            if (info.type === 'enum') {
                group.appendChild(createParamLabel(key, info.description));
                const sel = document.createElement('select');
                for (const o of info.options) { const op = document.createElement('option'); op.value = o; op.textContent = o; if (o === val) op.selected = true; sel.appendChild(op); }
                sel.addEventListener('change', () => { layer.params[key] = sel.value; });
                group.appendChild(sel);
            } else if (info.type === 'multi_enum') {
                group.appendChild(createParamLabel(key, info.description));
                const cg = document.createElement('div'); cg.className = 'chip-group';
                const selected = new Set(Array.isArray(val) ? val : []);
                for (const o of info.options) {
                    const chip = document.createElement('span');
                    chip.className = 'chip' + (selected.has(o) ? ' selected' : '');
                    chip.textContent = o;
                    chip.addEventListener('click', () => {
                        if (selected.has(o)) { selected.delete(o); chip.classList.remove('selected'); }
                        else { selected.add(o); chip.classList.add('selected'); }
                        layer.params[key] = Array.from(selected);
                    });
                    cg.appendChild(chip);
                }
                group.appendChild(cg);
            } else if (info.type === 'boolean') {
                const row = document.createElement('div'); row.className = 'toggle-row';
                row.appendChild(createParamLabel(key, info.description));
                const toggle = document.createElement('label');
                toggle.className = 'toggle';
                toggle.innerHTML = '<input type="checkbox" ' + (val ? 'checked' : '') + '><span class="toggle-track"></span>';
                row.appendChild(toggle);
                row.querySelector('input').addEventListener('change', (e) => { layer.params[key] = e.target.checked; });
                group.appendChild(row);
            } else if (info.type === 'integer' || info.type === 'float') {
                group.appendChild(createParamLabel(key, info.description));
                const wrap = document.createElement('div'); wrap.className = 'number-input';
                const step = info.step || (info.type === 'float' ? 0.1 : 1);
                const mn = info.min !== undefined ? info.min : 0;
                const mx = info.max !== undefined ? info.max : 99999;
                const dec = document.createElement('button'); dec.textContent = '−'; dec.type = 'button';
                const inp = document.createElement('input'); inp.type = 'number';
                inp.value = info.type === 'float' ? parseFloat(val).toFixed(2) : val;
                inp.step = step; inp.min = mn; inp.max = mx;
                const inc = document.createElement('button'); inc.textContent = '+'; inc.type = 'button';
                const upd = () => { let v = parseFloat(inp.value); if (isNaN(v)) v = info.default; v = Math.max(mn, Math.min(mx, v)); if (info.type === 'integer') v = Math.round(v); layer.params[key] = v; inp.value = info.type === 'float' ? v.toFixed(2) : v; };
                dec.addEventListener('click', () => { inp.value = parseFloat(inp.value) - step; upd(); });
                inc.addEventListener('click', () => { inp.value = parseFloat(inp.value) + step; upd(); });
                inp.addEventListener('change', upd); inp.addEventListener('blur', upd);
                wrap.appendChild(dec); wrap.appendChild(inp); wrap.appendChild(inc);
                group.appendChild(wrap);
            } else if (info.type === 'color') {
                group.appendChild(createParamLabel(key, info.description));
                const row = document.createElement('div'); row.className = 'color-row';
                const sw = document.createElement('div'); sw.className = 'color-swatch';
                const ci = document.createElement('input'); ci.type = 'color'; ci.value = rgbToHex(val);
                const hl = document.createElement('span'); hl.className = 'color-hex'; hl.textContent = rgbToHex(val);
                ci.addEventListener('input', () => { layer.params[key] = hexToRgb(ci.value); hl.textContent = ci.value; });
                sw.appendChild(ci); row.appendChild(sw); row.appendChild(hl);
                group.appendChild(row);
            } else if (info.type === 'string') {
                group.appendChild(createParamLabel(key, info.description));
                const ti = document.createElement('input'); ti.type = 'text'; ti.value = val;
                ti.addEventListener('change', () => { layer.params[key] = ti.value; });
                group.appendChild(ti);
            } else {
                group.appendChild(createParamLabel(key, info.description));
                const fallback = document.createElement('span');
                fallback.style.cssText = 'font-size:12px;color:var(--text-muted);';
                fallback.textContent = JSON.stringify(val);
                group.appendChild(fallback);
            }
            content.appendChild(group);
        }
    }

    function init(meta, order) {
        layersMeta = meta;
        defaultOrder = order;
        pipeline = defaultOrder.map(name => ({ name, params: getDefaultParams(name) }));

        $('addLayerBtn').addEventListener('click', (e) => { e.stopPropagation(); $('addLayerMenu').classList.toggle('open'); });
        document.addEventListener('click', () => { $('addLayerMenu').classList.remove('open'); });
        $('closeParamsBtn').addEventListener('click', () => { activeLayerIdx = -1; $('paramsPanel').style.display = 'none'; renderPipeline(); });

        renderPipeline();
    }

    function setPipeline(order, layerParams) {
        pipeline = order.map(name => ({ name, params: layerParams[name] || getDefaultParams(name) }));
        activeLayerIdx = -1;
        $('paramsPanel').style.display = 'none';
        renderPipeline();
    }

    function resetToDefaults() {
        pipeline = defaultOrder.map(name => ({ name, params: getDefaultParams(name) }));
        activeLayerIdx = -1;
        $('paramsPanel').style.display = 'none';
        renderPipeline();
    }

    return {
        init: init,
        setPipeline: setPipeline,
        resetToDefaults: resetToDefaults,
        renderPipeline: renderPipeline,
        getOrder: function () { return pipeline.map(l => l.name); },
        getLayerParams: function () { const p = {}; for (const l of pipeline) p[l.name] = { ...l.params }; return p; },
        getCount: function () { return pipeline.length; },
        rgbToHex: rgbToHex,
    };
})();
