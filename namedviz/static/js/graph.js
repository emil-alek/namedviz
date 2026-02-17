/**
 * D3 force-directed graph for namedviz.
 */
const Graph = (() => {
    const REL_COLORS = {
        master_slave: '#5b8af5',
        also_notify: '#f5a623',
        allow_transfer: '#22c997',
        forward: '#b07ae8',
        peer: '#f06292',
    };

    const ZONE_TYPE_COLORS = {
        master: '#6c63ff',
        slave: '#22c997',
        forward: '#b07ae8',
    };
    const ZONE_TYPE_FALLBACK = '#5a5a7a';

    let svg, container, simulation;
    let linkElements, nodeElements, labelElements;
    let graphData = null;
    let onNodeClick = null;
    let onLinkClick = null;

    const pie = d3.pie().sort(null).value(d => d.value);
    const nodeRadius = d => d.type === 'server' ? 14 : 5;

    function init(svgSelector, callbacks = {}) {
        onNodeClick = callbacks.onNodeClick || null;
        onLinkClick = callbacks.onLinkClick || null;

        svg = d3.select(svgSelector);
        svg.selectAll('*').remove();

        // Arrow markers for each relationship type
        const defs = svg.append('defs');
        Object.entries(REL_COLORS).forEach(([type, color]) => {
            defs.append('marker')
                .attr('id', `arrow-${type}`)
                .attr('viewBox', '0 -5 10 10')
                .attr('refX', 10)
                .attr('refY', 0)
                .attr('markerWidth', 8)
                .attr('markerHeight', 8)
                .attr('orient', 'auto')
                .append('path')
                .attr('d', 'M0,-4L10,0L0,4')
                .attr('fill', color);
        });

        container = svg.append('g').attr('class', 'graph-container');

        // Zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.2, 5])
            .on('zoom', (event) => {
                container.attr('transform', event.transform);
            });
        svg.call(zoom);

        return { svg, container };
    }

    function _renderDonut(g, d) {
        const r = nodeRadius(d);
        const counts = d.zone_counts || {};
        const entries = Object.entries(counts);

        if (entries.length === 0) {
            // No zones: render a thin gray ring
            const arcGen = d3.arc().innerRadius(r * 0.55).outerRadius(r);
            g.append('path')
                .attr('d', arcGen({ startAngle: 0, endAngle: 2 * Math.PI }))
                .attr('fill', ZONE_TYPE_FALLBACK)
                .attr('stroke', '#7a7a9a')
                .attr('stroke-width', 1);
            return;
        }

        const pieData = pie(entries.map(([key, value]) => ({ key, value })));
        const arcGen = d3.arc().innerRadius(r * 0.55).outerRadius(r);

        g.selectAll('path')
            .data(pieData)
            .join('path')
            .attr('d', arcGen)
            .attr('fill', seg => ZONE_TYPE_COLORS[seg.data.key] || ZONE_TYPE_FALLBACK)
            .attr('stroke', 'rgba(0,0,0,0.3)')
            .attr('stroke-width', 0.5);
    }

    function _computeCurveOffsets(links) {
        // Group links by unordered node pair
        const pairGroups = {};
        links.forEach((l, i) => {
            const sId = l.source.id || l.source;
            const tId = l.target.id || l.target;
            // Canonical key: alphabetically smaller first
            const key = sId < tId ? `${sId}|${tId}` : `${tId}|${sId}`;
            if (!pairGroups[key]) pairGroups[key] = [];
            pairGroups[key].push(i);
            l._pairReversed = sId > tId;
        });

        links.forEach(l => { l._curveOffset = 0; });
        Object.values(pairGroups).forEach(indices => {
            const n = indices.length;
            if (n <= 1) return;
            indices.forEach((idx, j) => {
                const base = (j - (n - 1) / 2) * 30;
                links[idx]._curveOffset = links[idx]._pairReversed ? -base : base;
            });
        });
    }

    function _linkPath(d) {
        const sx = d.source.x, sy = d.source.y;
        const tx = d.target.x, ty = d.target.y;
        const dx = tx - sx, dy = ty - sy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const targetR = nodeRadius(d.target) + 2;

        if (d._curveOffset === 0) {
            // Straight line
            const ex = tx - (dx / dist) * targetR;
            const ey = ty - (dy / dist) * targetR;
            return `M${sx},${sy}L${ex},${ey}`;
        }

        // Perpendicular normal
        const nx = -dy / dist, ny = dx / dist;
        const cx = (sx + tx) / 2 + nx * d._curveOffset;
        const cy = (sy + ty) / 2 + ny * d._curveOffset;

        // Trim endpoint along tangent at t=1 (from control to target)
        const tdx = tx - cx, tdy = ty - cy;
        const tdist = Math.sqrt(tdx * tdx + tdy * tdy) || 1;
        const ex = tx - (tdx / tdist) * targetR;
        const ey = ty - (tdy / tdist) * targetR;

        return `M${sx},${sy}Q${cx},${cy} ${ex},${ey}`;
    }

    function render(data, filters = {}) {
        graphData = data;
        if (!container) return;

        // Filter links
        let links = data.links.filter(l => {
            if (filters.relTypes && !filters.relTypes.has(l.rel_type)) return false;
            if (filters.servers) {
                if (!filters.servers.has(l.source.id || l.source) &&
                    !filters.servers.has(l.target.id || l.target))
                    return false;
            }
            if (filters.zoneSearch) {
                const q = filters.zoneSearch.toLowerCase();
                if (!l.zones.some(z => z.toLowerCase().includes(q))) return false;
            }
            return true;
        });

        // Get connected node IDs
        const connectedNodes = new Set();
        links.forEach(l => {
            connectedNodes.add(l.source.id || l.source);
            connectedNodes.add(l.target.id || l.target);
        });

        // Filter nodes - always show servers, filter external by connectivity
        let nodes = data.nodes.filter(n => {
            if (filters.servers && n.type === 'server' && !filters.servers.has(n.id)) return false;
            if (n.type === 'external' && !connectedNodes.has(n.id)) return false;
            return true;
        });

        // Clear
        container.selectAll('.link').remove();
        container.selectAll('.node').remove();
        container.selectAll('.node-label').remove();

        // Edge thickness based on zone count
        const maxCount = Math.max(1, ...links.map(l => l.count));
        const thicknessScale = d3.scaleLinear().domain([1, maxCount]).range([1, 5]);

        // Pre-compute curve offsets for parallel/bidirectional links
        _computeCurveOffsets(links);

        // Links — <path> elements with Bézier curves
        linkElements = container.selectAll('.link')
            .data(links)
            .join('path')
            .attr('class', d => `link link-${d.rel_type}`)
            .attr('stroke-width', d => thicknessScale(d.count))
            .attr('marker-end', d => `url(#arrow-${d.rel_type})`)
            .on('mouseover', (event, d) => _showTooltip(event, _linkTooltipHtml(d)))
            .on('mousemove', (event) => _moveTooltip(event))
            .on('mouseout', () => _hideTooltip())
            .on('click', (event, d) => { event.stopPropagation(); if (onLinkClick) onLinkClick(d); });

        // Nodes — all <g> groups
        nodeElements = container.selectAll('.node')
            .data(nodes)
            .join('g')
            .attr('class', d => `node node-${d.type}`)
            .each(function(d) {
                const g = d3.select(this);
                if (d.type === 'server') {
                    _renderDonut(g, d);
                } else {
                    const s = 10;
                    g.append('rect')
                        .attr('width', s).attr('height', s)
                        .attr('x', -s / 2).attr('y', -s / 2)
                        .attr('class', 'node-external-rect');
                }
            })
            .on('mouseover', (event, d) => {
                _highlightConnected(d.id);
                _showTooltip(event, _nodeTooltipHtml(d));
            })
            .on('mousemove', (event) => _moveTooltip(event))
            .on('mouseout', () => {
                _clearHighlight();
                _hideTooltip();
            })
            .on('click', (event, d) => { event.stopPropagation(); if (onNodeClick) onNodeClick(d); })
            .call(d3.drag()
                .on('start', _dragStarted)
                .on('drag', _dragged)
                .on('end', _dragEnded)
            );

        // Labels
        labelElements = container.selectAll('.node-label')
            .data(nodes)
            .join('text')
            .attr('class', 'node-label')
            .attr('dy', d => d.type === 'server' ? nodeRadius(d) + 14 : 20)
            .text(d => d.id);

        // Simulation
        const svgRect = svg.node().getBoundingClientRect();
        const cx = svgRect.width / 2;
        const cy = svgRect.height / 2;

        simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(links).id(d => d.id).distance(150))
            .force('charge', d3.forceManyBody().strength(-400))
            .force('center', d3.forceCenter(cx, cy))
            .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 20))
            .on('tick', () => {
                linkElements.attr('d', _linkPath);

                nodeElements
                    .attr('transform', d => `translate(${d.x},${d.y})`);

                labelElements
                    .attr('x', d => d.x)
                    .attr('y', d => d.y);
            });
    }

    function _dragStarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    function _dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    function _dragEnded(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }

    function _highlightConnected(nodeId) {
        linkElements.classed('dimmed', d =>
            (d.source.id || d.source) !== nodeId &&
            (d.target.id || d.target) !== nodeId
        );
        nodeElements.classed('dimmed', d => {
            if (d.id === nodeId) return false;
            const connected = graphData.links.some(l =>
                ((l.source.id || l.source) === nodeId && (l.target.id || l.target) === d.id) ||
                ((l.target.id || l.target) === nodeId && (l.source.id || l.source) === d.id)
            );
            return !connected;
        });
    }

    function _clearHighlight() {
        if (linkElements) linkElements.classed('dimmed', false);
        if (nodeElements) nodeElements.classed('dimmed', false);
    }

    function _showTooltip(event, html) {
        const tooltip = document.getElementById('tooltip');
        tooltip.innerHTML = html;
        tooltip.classList.add('visible');
        _moveTooltip(event);
    }

    function _moveTooltip(event) {
        const tooltip = document.getElementById('tooltip');
        tooltip.style.left = (event.pageX + 12) + 'px';
        tooltip.style.top = (event.pageY - 12) + 'px';
    }

    function _hideTooltip() {
        document.getElementById('tooltip').classList.remove('visible');
    }

    function _nodeTooltipHtml(d) {
        if (d.type === 'server') {
            const counts = d.zone_counts || {};
            const roleLabel = (d.role || 'server').charAt(0).toUpperCase() + (d.role || 'server').slice(1);
            let html = `<h4>${d.id}</h4>`;
            html += `<div class="tooltip-type">${roleLabel}</div>`;
            if (d.listen_on && d.listen_on.length) {
                html += `<div class="tooltip-ips">${d.listen_on.join(', ')}</div>`;
            }
            html += '<ul>';
            Object.entries(counts).forEach(([t, c]) => {
                const color = ZONE_TYPE_COLORS[t] || ZONE_TYPE_FALLBACK;
                html += `<li><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>${t}: ${c} zone(s)</li>`;
            });
            html += '</ul>';
            return html;
        }
        let html = `<h4>${d.id}</h4><div class="tooltip-type">External IP</div>`;
        if (d.views && d.views.length) {
            html += `<div class="tooltip-views">Views: ${d.views.join(', ')}</div>`;
        }
        return html;
    }

    function _linkTooltipHtml(d) {
        const src = d.source.id || d.source;
        const tgt = d.target.id || d.target;
        const typeLabel = d.rel_type.replace('_', ' ');
        let html = `<h4>${src} &rarr; ${tgt}</h4>`;
        html += `<p>${typeLabel} (${d.count} zone(s))</p><ul>`;
        d.zones.slice(0, 10).forEach(z => { html += `<li>${z}</li>`; });
        if (d.zones.length > 10) html += `<li>...and ${d.zones.length - 10} more</li>`;
        html += '</ul>';
        return html;
    }

    function getSvgElement() {
        return svg ? svg.node() : null;
    }

    return { init, render, getSvgElement, REL_COLORS, ZONE_TYPE_COLORS };
})();
