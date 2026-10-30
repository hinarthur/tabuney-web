/* 首頁 hero 的輕量 Step Flow 示範。
   資料是伺服器端帶來的真實已發布流程圖（6 nimmt! Default ruleset），已依介面語言在地化
   （見 game.selectors.hero_step_flow）。刻意不掛 React Flow：只畫單一節點，點分支／上下步切換。
   分支提示字由 data-caption-branch 帶入，沿用流程圖頁的 game.flowchart.tour.choose。 */
(function () {
    const root = document.getElementById('heroVisual');
    const dataEl = document.getElementById('heroFlowData');
    if (!root || !dataEl) return;

    const flow = JSON.parse(dataEl.textContent);
    const { nodes, out } = flow;

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const shape = document.getElementById('heroStepShape');
    const textGroup = document.getElementById('heroStepText');
    const branchBox = document.getElementById('heroBranches');
    const btn = (id) => document.getElementById(id);
    const captionBranch = root.dataset.captionBranch;

    let current = flow.initial;
    let history = [];

    function el(tag, attrs, text) {
        const node = document.createElementNS(SVG_NS, tag);
        for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
        if (text !== undefined) node.textContent = text;
        return node;
    }

    // 依實際渲染寬度折行：拉丁字詞整個移動，中日文逐字。
    // 先量再折，才不會像固定字數折行那樣讓長字溢出節點。
    function wrapText(value, size, maxWidth, host = textGroup) {
        const probe = el('text', { 'font-size': size, 'font-family': 'inherit', 'font-weight': 500, visibility: 'hidden' });
        host.append(probe);
        const width = (str) => { probe.textContent = str; return probe.getComputedTextLength(); };
        // 拉丁字母／數字連續一段算一個詞（不拆開），其他字元（中日文）逐字，空白單獨成 token。
        // 不能只看「有沒有空格」：中文裡夾著「4」「1」這種數字加空格時，整句會被當成英文按空白切，
        // 長長一串中文就成了折不開的單一 token。
        const tokens = value.match(/[\p{Script=Latin}\p{N}'’.,;:!?≥≤+\-–\/&()%]+|\s+|\S/gu) || [];
        // 行首不該出現的標點（避頭點）：留在上一行尾端
        const noLineStart = /^[，。、；：！？）」』】》,.;:!?)]$/;
        const lines = [];
        let line = '';
        for (const token of tokens) {
            if (/^\s+$/.test(token) && !line) continue;   // 換行後的空白不要留在行首
            const next = line + token;
            if (line.trim() && width(next.trimEnd()) > maxWidth && !noLineStart.test(token)) {
                lines.push(line.trimEnd());
                line = /^\s+$/.test(token) ? '' : token;
            } else {
                line = next;
            }
        }
        if (line.trim()) lines.push(line.trimEnd());
        const widest = Math.max(...lines.map(width));
        probe.remove();
        return { lines, widest };
    }

    // 從大字級往下找，第一個「每行放得下、總高也放得下」的字級
    function fitText(value, maxWidth, maxHeight, host = textGroup, from = 29, to = 13) {
        let result;
        for (let size = from; size >= to; size -= 1) {
            const { lines, widest } = wrapText(value, size, maxWidth, host);
            result = { lines, size };
            if (widest <= maxWidth && lines.length * size * 1.2 <= maxHeight) break;
        }
        return result;
    }

    function go(id, record = true) {
        if (!nodes[id]) return;
        if (record) history.push(current);
        current = id;
        render();
    }

    // 配色與真實流程圖一致：直接用 theme.css 的 --fc-*。
    // 動作節點依階段（1 準備／2 遊戲流程／3 終局）換色，沒有階段才用一般動作色。
    function nodeStyle(n) {
        if (n.kind === 'start') return { bg: 'var(--fc-oval-start-bg)', border: 'var(--fc-oval-start-border)', text: 'var(--fc-oval-start-text)' };
        if (n.kind === 'end') return { bg: 'var(--fc-oval-end-bg)', border: 'var(--fc-oval-end-border)', text: 'var(--fc-oval-end-text)' };
        if (n.kind === 'decision') return { bg: 'var(--fc-diamond-bg)', border: 'var(--fc-diamond-border)', text: 'var(--fc-diamond-text)' };
        if (n.kind === 'parallel') return { bg: 'var(--fc-double-bg)', border: 'var(--fc-double-border)', text: 'var(--fc-double-text)' };
        if (n.phase) return { bg: `var(--fc-phase${n.phase}-bg)`, border: `var(--fc-phase${n.phase}-border)`, text: `var(--fc-phase${n.phase}-text)` };
        return { bg: 'var(--fc-action-bg)', border: 'var(--fc-action-border)', text: 'var(--fc-action-text)' };
    }

    function render() {
        const n = nodes[current];
        const edges = out[current] || [];
        const decision = n.kind === 'decision';
        const pill = n.kind === 'start' || n.kind === 'end';
        shape.replaceChildren();
        textGroup.replaceChildren();

        const c = nodeStyle(n);
        if (decision) {
            const points = '210,21 400,127 210,233 20,127';
            shape.append(
                el('polygon', { points, fill: c.bg, stroke: c.border, 'stroke-width': 3 }),
                el('polygon', { points, fill: 'url(#heroHatch)' })
            );
        } else if (n.kind === 'parallel') {
            // 雙線框：外框＋內縮一圈
            shape.append(
                el('rect', { x: 32, y: 46, width: 356, height: 158, rx: 14, fill: c.bg, stroke: c.border, 'stroke-width': 3 }),
                el('rect', { x: 42, y: 56, width: 336, height: 138, rx: 9, fill: 'none', stroke: c.border, 'stroke-width': 2 })
            );
        } else {
            shape.append(el('rect', { x: 32, y: 46, width: 356, height: 158, rx: pill ? 79 : 14, fill: c.bg, stroke: c.border, 'stroke-width': 3 }));
        }

        // 菱形文字限制在內接矩形（寬 60%、高 40%，和真實流程圖的 DiamondLabel 一致），字級往下縮到放得下；
        // 其他節點留出邊框內距
        const { lines, size } = decision ? fitText(n.label, 228, 85) : fitText(n.label, pill ? 280 : 310, 118);
        const lineH = size * 1.2;
        const firstY = 127 - ((lines.length - 1) * lineH) / 2;
        lines.forEach((line, i) => {
            textGroup.append(el('text', {
                x: 210, y: firstY + i * lineH,
                'text-anchor': 'middle', 'dominant-baseline': 'middle',
                fill: c.text, 'font-size': size, 'font-family': 'inherit', 'font-weight': 500,
            }, line));
        });

        // 多條出邊＝分支，用邊上的標籤（是／否…）當按鈕
        const branching = edges.length > 1;
        branchBox.replaceChildren();
        if (branching) {
            // 真的流程圖只有分支提示字，順序步驟與終點都不加說明
            const caption = document.createElement('span');
            caption.textContent = captionBranch;
            branchBox.append(caption);
            edges.forEach((edge, i) => {
                const b = document.createElement('button');
                b.type = 'button';
                b.className = 'hero-branch-btn';
                b.textContent = edge.label || String(i + 1);
                b.addEventListener('click', () => go(edge.to));
                branchBox.append(b);
            });
        }

        btn('heroPrev').disabled = !history.length;
        btn('heroNext').disabled = edges.length !== 1;
        btn('heroLast').disabled = current === flow.last;
    }

    // ── Full Flowchart：用同一份在地化資料畫出整張圖（座標與邊路徑都來自真實流程圖）──
    function renderFull() {
        const svg = document.getElementById('heroFullSvg');
        if (!svg || !flow.view) return;
        svg.setAttribute('viewBox', flow.view.join(' '));
        svg.replaceChildren();

        // 每種邊色一個箭頭
        const defs = el('defs');
        const strokes = [...new Set(flow.edges.map((e) => e.stroke))];
        strokes.forEach((stroke, i) => {
            const marker = el('marker', { id: `heroArrow${i}`, markerWidth: 7, markerHeight: 7, refX: 6, refY: 3.5, orient: 'auto' });
            marker.append(el('path', { d: 'M0 0L7 3.5L0 7z', fill: stroke }));
            defs.append(marker);
        });
        const hatch = el('pattern', { id: 'heroFullHatch', width: 7, height: 7, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' });
        hatch.append(el('path', { d: 'M0 0V7', stroke: 'var(--fc-diamond-text)', 'stroke-opacity': '.13', 'stroke-width': 1 }));
        defs.append(hatch);
        svg.append(defs);

        flow.edges.forEach((e) => {
            svg.append(el('path', { d: e.d, stroke: e.stroke, 'stroke-width': 1.6, fill: 'none', 'marker-end': `url(#heroArrow${strokes.indexOf(e.stroke)})` }));
        });
        flow.edges.forEach((e) => {
            if (!e.label || e.lx == null) return;
            svg.append(
                el('rect', { x: e.lx - 14, y: e.ly - 10, width: 28, height: 16, rx: 4, fill: 'var(--fc-edge-label-bg)' }),
                el('text', { x: e.lx, y: e.ly + 2, 'text-anchor': 'middle', 'font-size': 10, 'font-family': 'inherit', fill: e.stroke }, e.label)
            );
        });

        Object.values(nodes).forEach((n) => {
            const c = nodeStyle(n);
            const cx = n.x + n.w / 2;
            const cy = n.y + n.h / 2;
            const g = el('g');
            let box;   // 文字可用範圍
            if (n.kind === 'decision') {
                const points = `${cx},${n.y} ${n.x + n.w},${cy} ${cx},${n.y + n.h} ${n.x},${cy}`;
                g.append(el('polygon', { points, fill: c.bg, stroke: c.border, 'stroke-width': 1.5 }), el('polygon', { points, fill: 'url(#heroFullHatch)' }));
                box = [n.w * 0.6, n.h * 0.4];   // 內接矩形，和真實的 DiamondLabel 一致
            } else if (n.kind === 'parallel') {
                g.append(
                    el('rect', { x: n.x, y: n.y, width: n.w, height: n.h, rx: 6, fill: c.bg, stroke: c.border, 'stroke-width': 1.5 }),
                    el('rect', { x: n.x + 3.5, y: n.y + 3.5, width: n.w - 7, height: n.h - 7, rx: 4, fill: 'none', stroke: c.border, 'stroke-width': 1 })
                );
                box = [n.w - 28, n.h - 14];
            } else {
                const pill = n.kind === 'start' || n.kind === 'end';
                g.append(el('rect', { x: n.x, y: n.y, width: n.w, height: n.h, rx: pill ? n.h / 2 : 6, fill: c.bg, stroke: c.border, 'stroke-width': 1.5 }));
                box = [n.w - 24, n.h - 12];
            }
            const { lines, size } = fitText(n.label, box[0], box[1], svg, 12, 7);
            const lineH = size * 1.2;
            const firstY = cy - ((lines.length - 1) * lineH) / 2;
            lines.forEach((line, i) => {
                g.append(el('text', { x: cx, y: firstY + i * lineH, 'text-anchor': 'middle', 'dominant-baseline': 'middle', fill: c.text, 'font-size': size, 'font-family': 'inherit', 'font-weight': 600 }, line));
            });
            svg.append(g);
        });
    }

    btn('heroFirst').onclick = () => { history = []; current = flow.first; render(); };
    btn('heroPrev').onclick = () => { if (history.length) { current = history.pop(); render(); } };
    btn('heroNext').onclick = () => { const e = out[current] || []; if (e.length === 1) go(e[0].to); };
    btn('heroLast').onclick = () => go(flow.last);

    render();
    renderFull();
})();
