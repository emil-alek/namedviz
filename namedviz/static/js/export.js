/**
 * SVG and PNG export utilities.
 */
const Export = (() => {

    function downloadPng(svgElement, filename = 'namedviz.png', scale = 2) {
        const clone = svgElement.cloneNode(true);
        _inlineStyles(svgElement, clone);

        const rect = svgElement.getBoundingClientRect();
        clone.setAttribute('width', rect.width);
        clone.setAttribute('height', rect.height);
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

        const serializer = new XMLSerializer();
        const svgString = serializer.serializeToString(clone);
        const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(svgBlob);

        const img = new Image();
        img.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = rect.width * scale;
            canvas.height = rect.height * scale;
            const ctx = canvas.getContext('2d');
            ctx.scale(scale, scale);
            // Dark background
            ctx.fillStyle = '#1a1a2e';
            ctx.fillRect(0, 0, rect.width, rect.height);
            ctx.drawImage(img, 0, 0);
            _drawLegend(ctx, rect.width, rect.height);
            URL.revokeObjectURL(url);

            canvas.toBlob(blob => {
                _download(blob, filename);
            }, 'image/png');
        };
        img.src = url;
    }

    function _inlineStyles(source, target) {
        const sourceChildren = source.querySelectorAll('*');
        const targetChildren = target.querySelectorAll('*');

        for (let i = 0; i < sourceChildren.length && i < targetChildren.length; i++) {
            const computed = window.getComputedStyle(sourceChildren[i]);
            const style = targetChildren[i].style;

            for (const prop of ['fill', 'stroke', 'stroke-width', 'stroke-dasharray',
                               'opacity', 'font-size', 'font-family', 'text-anchor']) {
                const val = computed.getPropertyValue(prop);
                if (val) style.setProperty(prop, val);
            }
        }
    }

    function _drawLegend(ctx, width, height) {
        const { LINK_ITEMS, NODE_ITEMS } = Legend.getLegendItems();

        const hPad = 16, vPad = 12, iconW = 30, gap = 10, itemH = 20, itemGap = 6, sepH = 17;
        const boxW = 185;
        const boxH = vPad + LINK_ITEMS.length * itemH + (LINK_ITEMS.length - 1) * itemGap
                   + sepH + NODE_ITEMS.length * itemH + (NODE_ITEMS.length - 1) * itemGap + vPad;

        const bx = 16;
        const by = height - 16 - boxH;

        // Background box
        ctx.save();
        ctx.fillStyle = 'rgba(22, 22, 37, 0.92)';
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(bx, by, boxW, boxH, 10);
        ctx.fill();
        ctx.stroke();

        ctx.font = '11px Inter, -apple-system, BlinkMacSystemFont, sans-serif';
        ctx.textBaseline = 'middle';

        let cy = by + vPad;

        // Link items
        LINK_ITEMS.forEach((item, i) => {
            const midY = cy + itemH / 2;
            ctx.save();
            ctx.setLineDash(item.dash ? item.dash.split(' ').map(Number) : []);
            ctx.strokeStyle = item.color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(bx + hPad, midY);
            ctx.lineTo(bx + hPad + iconW, midY);
            ctx.stroke();
            ctx.restore();
            ctx.fillStyle = '#8888a4';
            ctx.fillText(item.label, bx + hPad + iconW + gap, midY);
            cy += itemH + (i < LINK_ITEMS.length - 1 ? itemGap : 0);
        });

        // Separator
        cy += (sepH - 1) / 2;
        ctx.fillStyle = 'rgba(255, 255, 255, 0.06)';
        ctx.fillRect(bx + hPad, cy, boxW - hPad * 2, 1);
        cy += 1 + (sepH - 1) / 2;

        // Node items
        NODE_ITEMS.forEach((item, i) => {
            const midY = cy + itemH / 2;
            const cx = bx + hPad + iconW / 2;
            if (item.rect) {
                ctx.fillStyle = item.fill;
                ctx.strokeStyle = item.stroke;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.rect(cx - 5, midY - 5, 10, 10);
                ctx.fill();
                ctx.stroke();
            } else {
                ctx.save();
                ctx.fillStyle = item.color;
                ctx.beginPath();
                ctx.arc(cx, midY, 6, 0, Math.PI * 2, false);
                ctx.arc(cx, midY, 3, 0, Math.PI * 2, true);
                ctx.fill('evenodd');
                ctx.restore();
            }
            ctx.fillStyle = '#8888a4';
            ctx.fillText(item.label, bx + hPad + iconW + gap, midY);
            cy += itemH + (i < NODE_ITEMS.length - 1 ? itemGap : 0);
        });

        ctx.restore();
    }

    function _download(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    return { downloadPng };
})();
