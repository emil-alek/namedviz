/**
 * SVG and PNG export utilities.
 */
const Export = (() => {

    function downloadSvg(svgElement, filename = 'namedviz.svg') {
        const clone = svgElement.cloneNode(true);

        // Inline computed styles
        _inlineStyles(svgElement, clone);

        // Set explicit dimensions
        const rect = svgElement.getBoundingClientRect();
        clone.setAttribute('width', rect.width);
        clone.setAttribute('height', rect.height);
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

        const serializer = new XMLSerializer();
        const svgString = serializer.serializeToString(clone);
        const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });

        _download(blob, filename);
    }

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

    return { downloadSvg, downloadPng };
})();
