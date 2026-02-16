/**
 * D3 force-directed graph for namedviz.
 */
const Graph = (() => {
    const REL_COLORS = {
        master_slave: '#5b8af5',
        also_notify: '#f5a623',
        allow_transfer: '#22c997',
        forward: '#b07ae8',
    };

    const ROLE_COLORS = {
        master: '#6c63ff',
        slave: '#22c997',
        mixed: '#f5a623',
        other: '#5a5a7a',
    };

    let svg, container, simulation;
    let linkElements, nodeElements, labelElements;
    let graphData = null;
    let onNodeClick = null;
    let onLinkClick = null;

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
                .attr('refX', 20)
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

        // Links
        linkElements = container.selectAll('.link')
            .data(links)
            .join('line')
            .attr('class', d => `link link-${d.rel_type}`)
            .attr('stroke-width', d => thicknessScale(d.count))
            .attr('marker-end', d => `url(#arrow-${d.rel_type})`)
            .on('mouseover', (event, d) => _showTooltip(event, _linkTooltipHtml(d)))
            .on('mousemove', (event) => _moveTooltip(event))
            .on('mouseout', () => _hideTooltip())
            .on('click', (event, d) => { if (onLinkClick) onLinkClick(d); });

        // Nodes
        const nodeRadius = d => d.type === 'server' ? Math.max(8, 4 + d.zone_count * 1.5) : 5;

        nodeElements = container.selectAll('.node')
            .data(nodes)
            .join(enter => {
                return enter.append(d => {
                    const el = d.type === 'server'
                        ? document.createElementNS('http://www.w3.org/2000/svg', 'circle')
                        : document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                    return el;
                });
            })
            .attr('class', d => {
                let cls = `node node-${d.type}`;
                if (d.type === 'server' && d.role) cls += ` node-role-${d.role}`;
                return cls;
            })
            .each(function(d) {
                const el = d3.select(this);
                if (d.type === 'server') {
                    el.attr('r', nodeRadius(d));
                } else {
                    const s = 10;
                    el.attr('width', s).attr('height', s)
                      .attr('x', -s/2).attr('y', -s/2);
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
            .on('click', (event, d) => { if (onNodeClick) onNodeClick(d); })
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
                linkElements
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);

                nodeElements.each(function(d) {
                    const el = d3.select(this);
                    if (d.type === 'server') {
                        el.attr('cx', d.x).attr('cy', d.y);
                    } else {
                        el.attr('x', d.x - 5).attr('y', d.y - 5);
                    }
                });

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
            const zones = d.zones || [];
            const byType = {};
            zones.forEach(z => {
                byType[z.type] = (byType[z.type] || 0) + 1;
            });
            const roleLabel = (d.role || 'server').charAt(0).toUpperCase() + (d.role || 'server').slice(1);
            const roleColor = ROLE_COLORS[d.role] || '#888';
            let html = `<h4>${d.id}</h4>`;
            html += `<div class="tooltip-type" style="color:${roleColor}">${roleLabel}</div><ul>`;
            Object.entries(byType).forEach(([t, c]) => {
                html += `<li>${t}: ${c} zone(s)</li>`;
            });
            html += '</ul>';
            return html;
        }
        return `<h4>${d.id}</h4><div class="tooltip-type">External IP</div>`;
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

    return { init, render, getSvgElement, REL_COLORS, ROLE_COLORS };
})();
