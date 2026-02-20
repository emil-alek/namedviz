/**
 * Main application orchestration.
 */
(function() {
    const MAX_UPLOAD_FILES = 5000;
    const MAX_UPLOAD_BYTES = 500 * 1024 * 1024; // 500 MB

    let graphData = null;
    let uploadedFiles = []; // [{files: [File, ...], serverName}]
    let allLogs = []; // [{level, message}]
    let zoneSuggestionIndex = -1;

    async function init() {
        Graph.init('#graph-svg', {
            onNodeClick: showNodeDetail,
            onLinkClick: showLinkDetail,
        });
        Legend.render('legend');

        setupFilters();
        setupButtons();
        setupUpload();
        setupLogPanel();

        await loadGraph();
    }

    async function loadGraph() {
        try {
            const resp = await fetch('/api/graph');
            graphData = await resp.json();

            // Show upload overlay if no data loaded
            const overlay = document.getElementById('upload-overlay');
            if (!graphData.servers.length) {
                overlay.classList.remove('hidden');
            } else {
                overlay.classList.add('hidden');
            }

            buildServerFilters(graphData.servers);
            applyFiltersAndRender();
        } catch (err) {
            console.error('Failed to load graph:', err);
        }
    }

    function buildServerFilters(servers) {
        const container = document.getElementById('server-filters');
        container.innerHTML = '';
        const nodeMap = {};
        if (graphData && graphData.nodes) {
            graphData.nodes.forEach(n => { if (n.type === 'server') nodeMap[n.id] = n; });
        }
        servers.forEach(name => {
            const label = document.createElement('label');
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = true;
            cb.dataset.server = name;
            cb.addEventListener('change', applyFiltersAndRender);
            label.appendChild(cb);
            label.appendChild(document.createTextNode(' ' + name));
            const node = nodeMap[name];
            if (node && node.role) {
                const badge = document.createElement('span');
                badge.className = 'role-badge role-' + node.role;
                badge.textContent = node.role;
                label.appendChild(badge);
            }
            container.appendChild(label);
        });
    }

    function getActiveFilters() {
        const relTypes = new Set();
        document.querySelectorAll('[data-rel]').forEach(cb => {
            if (cb.checked) relTypes.add(cb.dataset.rel);
        });

        const servers = new Set();
        document.querySelectorAll('[data-server]').forEach(cb => {
            if (cb.checked) servers.add(cb.dataset.server);
        });

        const zoneSearch = document.getElementById('zone-search').value.trim();

        return { relTypes, servers, zoneSearch: zoneSearch || null };
    }

    function applyFiltersAndRender() {
        if (!graphData) return;
        const filters = getActiveFilters();
        Graph.render(graphData, filters);
    }

    function setupFilters() {
        document.querySelectorAll('[data-rel]').forEach(cb => {
            cb.addEventListener('change', applyFiltersAndRender);
        });
        const zoneInput = document.getElementById('zone-search');
        const zoneClear = document.getElementById('zone-clear');
        zoneInput.addEventListener('input', () => {
            applyFiltersAndRender();
            updateZoneSuggestions();
            zoneClear.classList.toggle('hidden', !zoneInput.value);
        });
        zoneInput.addEventListener('focus', updateZoneSuggestions);
        zoneInput.addEventListener('keydown', (e) => {
            const dropdown = document.getElementById('zone-suggestions');
            if (dropdown.classList.contains('hidden')) return;
            const items = dropdown.querySelectorAll('.zone-suggestion-item');
            if (!items.length) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                zoneSuggestionIndex = Math.min(zoneSuggestionIndex + 1, items.length - 1);
                items.forEach((el, i) => el.classList.toggle('highlighted', i === zoneSuggestionIndex));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                zoneSuggestionIndex = Math.max(zoneSuggestionIndex - 1, -1);
                items.forEach((el, i) => el.classList.toggle('highlighted', i === zoneSuggestionIndex));
            } else if (e.key === 'Enter' && zoneSuggestionIndex >= 0) {
                e.preventDefault();
                const zone = items[zoneSuggestionIndex].dataset.zone;
                zoneInput.value = zone;
                zoneClear.classList.remove('hidden');
                dropdown.classList.add('hidden');
                zoneSuggestionIndex = -1;
                applyFiltersAndRender();
            } else if (e.key === 'Escape') {
                dropdown.classList.add('hidden');
                zoneSuggestionIndex = -1;
            }
        });
        zoneInput.addEventListener('blur', () => {
            // Delay so mousedown on a suggestion item fires before we hide
            setTimeout(() => {
                document.getElementById('zone-suggestions').classList.add('hidden');
            }, 150);
        });
        zoneClear.addEventListener('click', () => {
            zoneInput.value = '';
            zoneClear.classList.add('hidden');
            document.getElementById('zone-suggestions').classList.add('hidden');
            applyFiltersAndRender();
            zoneInput.focus();
        });
    }

    function updateZoneSuggestions() {
        const input = document.getElementById('zone-search');
        const dropdown = document.getElementById('zone-suggestions');
        const q = input.value.trim().toLowerCase();

        if (!q || !graphData || !graphData.zones || !graphData.zones.length) {
            dropdown.classList.add('hidden');
            return;
        }

        // Deduplicate by (name, view) and filter by query
        const seen = new Set();
        const matches = [];
        graphData.zones.forEach(z => {
            const key = z.name + '|' + (z.view || '');
            if (!seen.has(key) && z.name.toLowerCase().includes(q)) {
                seen.add(key);
                matches.push(z);
            }
        });

        if (!matches.length) {
            dropdown.classList.add('hidden');
            return;
        }

        // Position dropdown below input using fixed coords
        const rect = input.getBoundingClientRect();
        dropdown.style.top = (rect.bottom + 2) + 'px';
        dropdown.style.left = rect.left + 'px';
        dropdown.style.width = rect.width + 'px';

        zoneSuggestionIndex = -1;
        dropdown.innerHTML = '';
        matches.slice(0, 25).forEach(z => {
            const item = document.createElement('div');
            item.className = 'zone-suggestion-item';
            item.dataset.zone = z.name;
            item.appendChild(document.createTextNode(z.name));
            if (z.view) {
                const viewSpan = document.createElement('span');
                viewSpan.className = 'zone-view';
                viewSpan.textContent = ' (' + z.view + ')';
                item.appendChild(viewSpan);
            }
            item.addEventListener('mousedown', (e) => {
                e.preventDefault(); // keep focus on input
                input.value = z.name;
                dropdown.classList.add('hidden');
                applyFiltersAndRender();
            });
            dropdown.appendChild(item);
        });
        dropdown.classList.remove('hidden');
    }

    function setupUpload() {
        const overlay = document.getElementById('upload-overlay');
        const dropZone = document.getElementById('upload-drop-zone');
        const fileInput = document.getElementById('upload-input');
        const folderInput = document.getElementById('upload-folder-input');
        const browseLink = document.getElementById('upload-browse');
        const browseFolderLink = document.getElementById('upload-browse-folder');
        const submitBtn = document.getElementById('upload-submit');
        // Show overlay
        document.getElementById('btn-upload').addEventListener('click', () => {
            overlay.classList.remove('hidden');
        });

        // Close overlay with Escape or clicking outside
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !overlay.classList.contains('hidden')) {
                overlay.classList.add('hidden');
            }
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.add('hidden');
            }
        });

        // Browse files link
        browseLink.addEventListener('click', (e) => {
            e.preventDefault();
            fileInput.click();
        });

        // Browse folder link
        browseFolderLink.addEventListener('click', (e) => {
            e.preventDefault();
            folderInput.click();
        });

        // Drop zone click
        dropZone.addEventListener('click', (e) => {
            if (e.target === dropZone || e.target.parentElement === dropZone) {
                fileInput.click();
            }
        });

        // Drag & drop
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleDrop(e.dataTransfer);
        });

        // File input change
        fileInput.addEventListener('change', () => {
            addFiles(Array.from(fileInput.files));
            fileInput.value = '';
        });

        // Folder input change
        folderInput.addEventListener('change', () => {
            addFolderFiles(Array.from(folderInput.files));
            folderInput.value = '';
        });

        // Submit
        submitBtn.addEventListener('click', async () => {
            if (!uploadedFiles.length) return;
            submitBtn.disabled = true;
            submitBtn.textContent = 'Parsing...';

            const formData = new FormData();
            uploadedFiles.forEach(entry => {
                entry.files.forEach(file => {
                    formData.append(entry.serverName, file, file._serverRelativePath || file.name);
                });
            });

            try {
                const resp = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData,
                });
                const result = await resp.json();
                if (result.status === 'ok') {
                    overlay.classList.add('hidden');
                    showLogs(result.logs || []);
                    await loadGraph();
                } else {
                    alert('Parse error: ' + (result.error || 'Unknown error'));
                }
            } catch (err) {
                alert('Upload failed: ' + err.message);
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Parse & Visualize';
            }
        });
    }

    function handleDrop(dataTransfer) {
        const items = dataTransfer.items;
        if (!items) {
            addFiles(Array.from(dataTransfer.files));
            return;
        }

        const entries = [];
        for (let i = 0; i < items.length; i++) {
            const entry = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
            if (entry) entries.push(entry);
        }

        // Check if any entry is a directory
        const hasDir = entries.some(e => e.isDirectory);
        if (!hasDir) {
            addFiles(Array.from(dataTransfer.files));
            return;
        }

        // Traverse directories and collect files with paths
        const filePromises = [];
        entries.forEach(entry => {
            filePromises.push(traverseEntry(entry, ''));
        });

        Promise.all(filePromises).then(results => {
            const allFiles = results.flat();
            addFolderFiles(allFiles);
        });
    }

    function traverseEntry(entry, basePath) {
        return new Promise((resolve) => {
            if (entry.isFile) {
                entry.file(file => {
                    // Attach the relative path so addFolderFiles can derive server name
                    file._relativePath = basePath ? basePath + '/' + file.name : file.name;
                    resolve([file]);
                });
            } else if (entry.isDirectory) {
                const reader = entry.createReader();
                const allEntries = [];

                // readEntries may not return all entries at once, so read in batches
                function readBatch() {
                    reader.readEntries(batch => {
                        if (batch.length === 0) {
                            const subPromises = allEntries.map(sub =>
                                traverseEntry(sub, basePath ? basePath + '/' + entry.name : entry.name)
                            );
                            Promise.all(subPromises).then(results => resolve(results.flat()));
                        } else {
                            allEntries.push(...batch);
                            readBatch();
                        }
                    });
                }
                readBatch();
            } else {
                resolve([]);
            }
        });
    }

    function addFolderFiles(files) {
        files = files.filter(f => !f.name.endsWith('.jnl') && !f.name.includes('dump.db'));
        if (!files.length) {
            alert('No files found in the selected folder.');
            return;
        }

        // Group files by top-level folder (= one server per folder).
        // Subfolders (e.g. zones/, includes/) belong to the same server.
        const groups = {};
        files.forEach(file => {
            const relPath = file.webkitRelativePath || file._relativePath || file.name;
            const parts = relPath.split('/').filter(Boolean);

            let serverName, innerPath;
            if (parts.length >= 2) {
                serverName = parts[0]; // top-level folder = server name
                innerPath = parts.slice(1).join('/'); // path within server folder
            } else {
                // Single file with no directory — derive from filename
                serverName = file.name.replace(/\.[^.]+$/i, '');
                if (serverName === 'named') serverName = `server${uploadedFiles.length + Object.keys(groups).length + 1}`;
                innerPath = file.name;
            }

            file._serverRelativePath = innerPath;
            if (!groups[serverName]) groups[serverName] = [];
            groups[serverName].push(file);
        });

        // Merge into uploadedFiles
        for (const [serverName, groupFiles] of Object.entries(groups)) {
            const existing = uploadedFiles.find(e => e.serverName === serverName);
            if (existing) {
                existing.files.push(...groupFiles);
            } else {
                uploadedFiles.push({ files: groupFiles, serverName });
            }
        }

        renderFileList();
    }

    function addFiles(files) {
        files = files.filter(f => !f.name.endsWith('.jnl') && !f.name.includes('dump.db'));
        files.forEach(file => {
            // Derive a default server name from filename
            let name = file.name.replace(/\.[^.]+$/i, '');
            if (name === 'named') name = `server${uploadedFiles.length + 1}`;
            uploadedFiles.push({ files: [file], serverName: name });
        });
        renderFileList();
    }

    function renderFileList() {
        const list = document.getElementById('upload-file-list');
        const submitBtn = document.getElementById('upload-submit');
        list.innerHTML = '';

        uploadedFiles.forEach((entry, i) => {
            const div = document.createElement('div');
            div.className = 'upload-file-item';

            const nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.value = entry.serverName;
            nameInput.placeholder = 'Server name';
            nameInput.addEventListener('input', () => {
                entry.serverName = nameInput.value.trim() || `server${i + 1}`;
            });

            const fileName = document.createElement('span');
            fileName.className = 'file-name';
            const names = entry.files.map(f => f._serverRelativePath || f.name);
            fileName.textContent = names.length === 1 ? names[0] : `${names.length} files`;
            fileName.title = names.join('\n');

            const removeBtn = document.createElement('button');
            removeBtn.className = 'file-remove';
            removeBtn.textContent = '\u00d7';
            removeBtn.addEventListener('click', () => {
                uploadedFiles.splice(i, 1);
                renderFileList();
            });

            div.appendChild(nameInput);
            div.appendChild(fileName);
            div.appendChild(removeBtn);
            list.appendChild(div);
        });

        // Count totals
        let totalFiles = 0, totalBytes = 0;
        uploadedFiles.forEach(entry => {
            entry.files.forEach(file => { totalFiles++; totalBytes += file.size; });
        });

        // Validate against server limits
        const errorEl = document.getElementById('upload-error');
        let errorMsg = null;
        if (totalFiles > MAX_UPLOAD_FILES) {
            errorMsg = `Too many files: ${totalFiles} selected, limit is ${MAX_UPLOAD_FILES}.`;
        } else if (totalBytes > MAX_UPLOAD_BYTES) {
            const mb = (totalBytes / 1024 / 1024).toFixed(1);
            errorMsg = `Upload too large: ${mb} MB, limit is ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.`;
        }

        if (errorMsg) {
            errorEl.textContent = errorMsg;
            errorEl.classList.remove('hidden');
            submitBtn.disabled = true;
        } else {
            errorEl.classList.add('hidden');
            submitBtn.disabled = uploadedFiles.length === 0;
        }
    }

    function setupButtons() {
        document.getElementById('btn-reset').addEventListener('click', async () => {
            try {
                await fetch('/api/reset', { method: 'POST' });
            } catch (err) {
                // Ignore — we clear frontend state regardless
            }
            graphData = null;
            uploadedFiles = [];
            // Clear graph SVG
            const svg = document.getElementById('graph-svg');
            svg.innerHTML = '';
            Graph.init('#graph-svg', {
                onNodeClick: showNodeDetail,
                onLinkClick: showLinkDetail,
            });
            // Clear sidebar filters
            document.getElementById('server-filters').innerHTML = '';
            document.getElementById('zone-search').value = '';
            document.getElementById('zone-clear').classList.add('hidden');
            document.getElementById('zone-suggestions').classList.add('hidden');
            // Clear file list in upload modal
            document.getElementById('upload-file-list').innerHTML = '';
            document.getElementById('upload-submit').disabled = true;
            // Hide detail panel
            document.getElementById('detail-panel').classList.add('hidden');
            // Hide log panel and clear logs
            allLogs = [];
            const logPanel = document.getElementById('log-panel');
            if (logPanel) logPanel.classList.add('hidden');
            // Show upload overlay
            document.getElementById('upload-overlay').classList.remove('hidden');
        });

        document.getElementById('btn-export-png').addEventListener('click', () => {
            const svgEl = Graph.getSvgElement();
            if (svgEl) Export.downloadPng(svgEl);
        });

        const detailPanel = document.getElementById('detail-panel');
        document.getElementById('detail-close').addEventListener('click', () => {
            detailPanel.classList.add('hidden');
        });
        document.addEventListener('click', (e) => {
            if (!detailPanel.classList.contains('hidden') && !detailPanel.contains(e.target)) {
                detailPanel.classList.add('hidden');
            }
        });

        // About modal
        const aboutOverlay = document.getElementById('about-overlay');
        document.getElementById('btn-about').addEventListener('click', () => {
            aboutOverlay.classList.remove('hidden');
        });
        document.getElementById('about-close').addEventListener('click', () => {
            aboutOverlay.classList.add('hidden');
        });
        aboutOverlay.addEventListener('click', (e) => {
            if (e.target === aboutOverlay) aboutOverlay.classList.add('hidden');
        });
    }

    async function showNodeDetail(node) {
        const panel = document.getElementById('detail-panel');
        const content = document.getElementById('detail-content');

        try {
            const resp = await fetch(`/api/server/${encodeURIComponent(node.id)}`);
            if (!resp.ok) {
                let extHtml = `<h2>${node.id}</h2><p>Unknown DNS Server</p>`;
                if (node.views && node.views.length) {
                    extHtml += `<p><strong>Views:</strong> ${node.views.join(', ')}</p>`;
                }
                content.innerHTML = extHtml;
                panel.classList.remove('hidden');
                return;
            }
            const data = await resp.json();

            // Compute per-view zone-type stats
            const viewStats = {}; // { viewName: { total, [zoneType]: count } }
            (data.zones || []).forEach(z => {
                const v = z.view || '(no view)';
                if (!viewStats[v]) viewStats[v] = { total: 0 };
                viewStats[v].total++;
                viewStats[v][z.type] = (viewStats[v][z.type] || 0) + 1;
            });
            const viewNames = Object.keys(viewStats);
            const hasViews = viewNames.some(v => v !== '(no view)');

            // Header with badges
            let html = `<div class="detail-header">`;
            html += `<h2>${data.name}</h2>`;

            // 1. IP always first
            if (data.listen_on && data.listen_on.length) {
                html += `<span class="detail-badge" data-tooltip="Listening addresses">${data.listen_on.join(', ')}</span>`;
            }

            // 2. Total views (if views present)
            if (hasViews) {
                const viewList = viewNames.join(', ');
                html += `<span class="detail-badge" data-tooltip="Views: ${viewList}">${viewNames.length} views</span>`;
            }

            // 3. Zones + per-view breakdown in one badge
            let zonesBadge = `${data.zone_count} zones`;
            let zonesTooltip = `Total zones`;
            if (hasViews) {
                const breakdown = viewNames.map(v => `${v}: ${viewStats[v].total}`).join(', ');
                zonesBadge += ` · ${breakdown}`;
                zonesTooltip = `Zones by view: ${breakdown}`;
            }
            html += `<span class="detail-badge" data-tooltip="${zonesTooltip}">${zonesBadge}</span>`;

            // 4. Global forwarding
            if (data.global_forwarders && data.global_forwarders.length) {
                html += `<span class="detail-badge" data-tooltip="Global forwarders">Global Forwarding: ${data.global_forwarders.join(', ')}</span>`;
            }
            html += `</div>`;

            // Zone table
            if (data.zones && data.zones.length) {
                html += '<table><tr><th>Zone</th><th>Type</th><th>View</th><th>Masters</th></tr>';
                data.zones.forEach(z => {
                    html += `<tr>
                        <td>${z.name}</td>
                        <td>${z.type}</td>
                        <td>${z.view || '-'}</td>
                        <td>${z.masters.join(', ') || '-'}</td>
                    </tr>`;
                });
                html += '</table>';
            }

            content.innerHTML = html;
            panel.classList.remove('hidden');
        } catch (err) {
            console.error('Failed to load server detail:', err);
        }
    }

    function showLinkDetail(link) {
        const panel = document.getElementById('detail-panel');
        const content = document.getElementById('detail-content');

        const src = link.source.id || link.source;
        const tgt = link.target.id || link.target;
        const typeLabel = link.rel_type.replace(/_/g, ' ');

        let html = `<h2>${src} &rarr; ${tgt}</h2>`;
        html += `<p>${typeLabel} &mdash; ${link.count} zone(s)</p>`;
        html += '<table><tr><th>Zone</th></tr>';
        link.zones.forEach(z => {
            html += `<tr><td>${z}</td></tr>`;
        });
        html += '</table>';

        content.innerHTML = html;
        panel.classList.remove('hidden');
    }

    function setupLogPanel() {
        const panel = document.getElementById('log-panel');
        if (!panel) return;
        document.getElementById('log-toggle').addEventListener('click', () => {
            panel.classList.toggle('collapsed');
        });
        document.getElementById('log-verbosity').addEventListener('change', () => {
            renderLogs();
        });
        document.getElementById('log-export').addEventListener('click', () => {
            exportLogs();
        });
    }

    function exportLogs() {
        if (!allLogs.length) return;
        const lines = allLogs.map(entry => `[${entry.level.toUpperCase()}] ${entry.message}`);
        const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'namedviz.log';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function showLogs(logs) {
        allLogs = logs || [];
        const panel = document.getElementById('log-panel');
        if (!panel) return;

        if (!allLogs.length) {
            panel.classList.add('hidden');
            return;
        }

        panel.classList.remove('hidden');
        panel.classList.remove('collapsed');
        renderLogs();
    }

    function renderLogs() {
        const body = document.getElementById('log-body');
        const count = document.getElementById('log-count');
        const verbosity = document.getElementById('log-verbosity').value;

        const filtered = allLogs.filter(entry => {
            if (verbosity === 'warn') return entry.level === 'warn';
            return true; // 'all'
        });

        body.innerHTML = '';
        filtered.forEach(entry => {
            const div = document.createElement('div');
            div.className = 'log-entry log-level-' + entry.level;
            div.textContent = entry.message;
            body.appendChild(div);
        });
        count.textContent = filtered.length;

        // If no entries match current filter, collapse but keep panel visible
        if (filtered.length === 0) {
            document.getElementById('log-panel').classList.add('collapsed');
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();
