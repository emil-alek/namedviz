/**
 * Main application orchestration.
 */
(function() {
    let graphData = null;
    let uploadedFiles = []; // [{file, serverName}]

    async function init() {
        Graph.init('#graph-svg', {
            onNodeClick: showNodeDetail,
            onLinkClick: showLinkDetail,
        });
        Legend.render('legend');

        setupFilters();
        setupButtons();
        setupUpload();

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
        document.getElementById('zone-search').addEventListener('input', applyFiltersAndRender);
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

        // Close overlay with Escape or clicking outside (only if data is already loaded)
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !overlay.classList.contains('hidden')) {
                if (graphData && graphData.servers.length) {
                    overlay.classList.add('hidden');
                }
            }
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay && graphData && graphData.servers.length) {
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
                formData.append(entry.serverName, entry.file);
            });

            try {
                const resp = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData,
                });
                const result = await resp.json();
                if (result.status === 'ok') {
                    overlay.classList.add('hidden');
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
        // Filter for .conf files
        const confFiles = files.filter(f => {
            const name = f.name || '';
            return name.endsWith('.conf') || name.endsWith('.txt');
        });

        if (!confFiles.length) {
            alert('No .conf files found in the selected folder.');
            return;
        }

        // Group by derived server name
        confFiles.forEach(file => {
            const relPath = file.webkitRelativePath || file._relativePath || file.name;
            const parts = relPath.split('/').filter(Boolean);

            let serverName;
            if (parts.length >= 2) {
                // e.g. "server1/named.conf" → "server1"
                // e.g. "configs/server1/named.conf" → "server1" (parent of file)
                serverName = parts[parts.length - 2];
            } else {
                // Single file with no directory — derive from filename
                serverName = file.name.replace(/\.(conf|txt)$/i, '');
                if (serverName === 'named') serverName = `server${uploadedFiles.length + 1}`;
            }

            // Avoid duplicate server names by checking existing entries
            const existing = uploadedFiles.find(e => e.serverName === serverName);
            if (!existing) {
                uploadedFiles.push({ file, serverName });
            }
        });

        renderFileList();
    }

    function addFiles(files) {
        files.forEach(file => {
            // Derive a default server name from filename
            let name = file.name.replace(/\.(conf|txt)$/i, '');
            if (name === 'named') name = `server${uploadedFiles.length + 1}`;
            uploadedFiles.push({ file, serverName: name });
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
            fileName.textContent = entry.file.name;

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

        submitBtn.disabled = uploadedFiles.length === 0;
    }

    function setupButtons() {
        document.getElementById('btn-reset').addEventListener('click', async () => {
            if (!confirm('Reset visualization and clear all uploaded data?')) return;
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
            // Clear file list in upload modal
            document.getElementById('upload-file-list').innerHTML = '';
            document.getElementById('upload-submit').disabled = true;
            // Hide detail panel
            document.getElementById('detail-panel').classList.add('hidden');
            // Show upload overlay
            document.getElementById('upload-overlay').classList.remove('hidden');
        });

        // Export dropdown
        const exportBtn = document.getElementById('btn-export');
        const exportDropdown = document.getElementById('export-dropdown');

        exportBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            exportDropdown.classList.toggle('hidden');
        });

        document.addEventListener('click', () => {
            exportDropdown.classList.add('hidden');
        });

        exportDropdown.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        document.getElementById('btn-export-svg').addEventListener('click', () => {
            const svgEl = Graph.getSvgElement();
            if (svgEl) Export.downloadSvg(svgEl);
            exportDropdown.classList.add('hidden');
        });

        document.getElementById('btn-export-png').addEventListener('click', () => {
            const svgEl = Graph.getSvgElement();
            if (svgEl) Export.downloadPng(svgEl);
            exportDropdown.classList.add('hidden');
        });

        document.getElementById('detail-close').addEventListener('click', () => {
            document.getElementById('detail-panel').classList.add('hidden');
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
                content.innerHTML = `<h2>${node.id}</h2><p>External IP address</p>`;
                panel.classList.remove('hidden');
                return;
            }
            const data = await resp.json();

            let html = `<h2>${data.name}</h2>`;
            html += `<p>${data.zone_count} zone(s)</p>`;

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

            if (data.global_forwarders.length) {
                html += `<p><strong>Global forwarders:</strong> ${data.global_forwarders.join(', ')}</p>`;
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

    document.addEventListener('DOMContentLoaded', init);
})();
