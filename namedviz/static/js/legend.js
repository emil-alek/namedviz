/**
 * Legend component for the graph.
 */
const Legend = (() => {
    const LINK_ITEMS = [
        { type: 'master_slave', label: 'Master / Slave', color: '#5b8af5', dash: '' },
        { type: 'also_notify', label: 'Also Notify', color: '#f5a623', dash: '6 3' },
        { type: 'allow_transfer', label: 'Allow Transfer', color: '#22c997', dash: '2 3' },
        { type: 'forward', label: 'Forward', color: '#b07ae8', dash: '' },
    ];

    const NODE_ITEMS = [
        { key: 'master', label: 'Master zones', color: '#6c63ff' },
        { key: 'slave', label: 'Slave zones', color: '#22c997' },
        { key: 'forward', label: 'Forward zones', color: '#b07ae8' },
        { key: 'external', label: 'External IP', fill: '#3a3a52', stroke: '#55556e', rect: true },
    ];

    function render(containerId) {
        const el = document.getElementById(containerId);
        el.innerHTML = '';

        // Link types
        LINK_ITEMS.forEach(item => {
            const div = document.createElement('div');
            div.className = 'legend-item';

            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('width', '30');
            svg.setAttribute('height', '10');
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', '0');
            line.setAttribute('y1', '5');
            line.setAttribute('x2', '30');
            line.setAttribute('y2', '5');
            line.setAttribute('stroke', item.color);
            line.setAttribute('stroke-width', '2');
            if (item.dash) line.setAttribute('stroke-dasharray', item.dash);
            svg.appendChild(line);

            const label = document.createElement('span');
            label.textContent = item.label;

            div.appendChild(svg);
            div.appendChild(label);
            el.appendChild(div);
        });

        // Separator
        const sep = document.createElement('div');
        sep.className = 'legend-separator';
        el.appendChild(sep);

        // Node types
        NODE_ITEMS.forEach(item => {
            const div = document.createElement('div');
            div.className = 'legend-item';

            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('width', '30');
            svg.setAttribute('height', '14');

            if (item.rect) {
                const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                rect.setAttribute('x', '10');
                rect.setAttribute('y', '2');
                rect.setAttribute('width', '10');
                rect.setAttribute('height', '10');
                rect.setAttribute('rx', '1');
                rect.setAttribute('fill', item.fill);
                rect.setAttribute('stroke', item.stroke);
                rect.setAttribute('stroke-width', '1');
                svg.appendChild(rect);
            } else {
                // Small donut arc preview
                const outerR = 6;
                const innerR = 3;
                // Full-ring arc path
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                const cx = 15, cy = 7;
                const d = [
                    `M${cx},${cy - outerR}`,
                    `A${outerR},${outerR} 0 1,1 ${cx},${cy + outerR}`,
                    `A${outerR},${outerR} 0 1,1 ${cx},${cy - outerR}`,
                    'Z',
                    `M${cx},${cy - innerR}`,
                    `A${innerR},${innerR} 0 1,0 ${cx},${cy + innerR}`,
                    `A${innerR},${innerR} 0 1,0 ${cx},${cy - innerR}`,
                    'Z',
                ].join(' ');
                path.setAttribute('d', d);
                path.setAttribute('fill', item.color);
                path.setAttribute('fill-rule', 'evenodd');
                svg.appendChild(path);
            }

            const label = document.createElement('span');
            label.textContent = item.label;

            div.appendChild(svg);
            div.appendChild(label);
            el.appendChild(div);
        });
    }

    return { render };
})();
