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
        { role: 'master', label: 'Master', fill: '#6c63ff', stroke: '#8b84ff' },
        { role: 'slave', label: 'Slave', fill: '#22c997', stroke: '#3de8b4' },
        { role: 'mixed', label: 'Mixed', fill: '#f5a623', stroke: '#ffc040' },
        { role: 'external', label: 'External IP', fill: '#3a3a52', stroke: '#55556e', rect: true },
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
                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', '15');
                circle.setAttribute('cy', '7');
                circle.setAttribute('r', '6');
                circle.setAttribute('fill', item.fill);
                circle.setAttribute('stroke', item.stroke);
                circle.setAttribute('stroke-width', '1.5');
                svg.appendChild(circle);
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
