/**
 * SEO Scraper Dashboard - jQuery SPA
 */

(function($) {
    'use strict';

    // ==========================================================================
    // Configuration & State
    // ==========================================================================
    const API = {
        stats: '/dashboard/api/stats',
        logs: '/dashboard/api/logs',
        log: (id) => `/dashboard/api/logs/${id}`,
        rescrape: (id) => `/dashboard/rescrape/${id}`,
        exportCsv: '/dashboard/export/csv'
    };

    let currentPage = 'index';
    let currentFilters = {
        page: 1,
        per_page: 20,
        status: '',
        content_type: '',
        url_search: '',
        search: ''
    };

    // ==========================================================================
    // Utility Functions
    // ==========================================================================
    function formatDate(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleDateString('fr-FR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    function formatDuration(ms) {
        if (ms == null) return '-';
        if (ms < 1000) return `${ms}ms`;
        return `${(ms / 1000).toFixed(1)}s`;
    }

    function formatSize(size) {
        if (size == null || size === 0) return '-';
        if (size < 1000) return `${size}`;
        if (size < 1000000) return `${(size / 1000).toFixed(1)}K`;
        return `${(size / 1000000).toFixed(1)}M`;
    }

    function truncateUrl(url, maxLength = 50) {
        if (!url) return '-';
        if (url.length <= maxLength) return url;
        return url.substring(0, maxLength - 3) + '...';
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showLoading() {
        $('#loading').removeClass('hidden');
    }

    function hideLoading() {
        $('#loading').addClass('hidden');
    }

    function showNotification(message, type = 'info') {
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            info: 'bg-blue-500',
            warning: 'bg-yellow-500'
        };

        const $notification = $(`
            <div class="fixed bottom-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50">
                ${escapeHtml(message)}
            </div>
        `);

        $('body').append($notification);

        setTimeout(() => {
            $notification.fadeOut(300, function() { $(this).remove(); });
        }, 3000);
    }

    function getStatusBadge(status) {
        const badges = {
            success: '<span class="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">Succes</span>',
            error: '<span class="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800">Erreur</span>',
            timeout: '<span class="px-2 py-1 text-xs font-medium rounded-full bg-yellow-100 text-yellow-800">Timeout</span>'
        };
        return badges[status] || badges.error;
    }

    function getTypeBadge(contentType) {
        const badges = {
            pdf: '<span class="px-2 py-1 text-xs font-medium rounded-full bg-purple-100 text-purple-800">PDF</span>',
            spa: '<span class="px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">SPA</span>',
            html: '<span class="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800">HTML</span>'
        };
        return badges[contentType] || badges.html;
    }

    function getHttpStatusClass(code) {
        if (!code) return 'text-gray-500';
        if (code >= 400) return 'text-red-600';
        if (code >= 300) return 'text-yellow-600';
        return 'text-green-600';
    }

    // ==========================================================================
    // API Calls
    // ==========================================================================
    function fetchStats() {
        return $.get(API.stats);
    }

    function fetchLogs(params = {}) {
        const queryParams = $.param({
            page: params.page || 1,
            per_page: params.per_page || 20,
            ...(params.status && { status: params.status }),
            ...(params.content_type && { content_type: params.content_type }),
            ...(params.url_search && { url_search: params.url_search }),
            ...(params.search && { search: params.search })
        });
        return $.get(`${API.logs}?${queryParams}`);
    }

    function fetchLog(id) {
        return $.get(API.log(id));
    }

    function rescrape(id) {
        return $.post(API.rescrape(id));
    }

    // ==========================================================================
    // Render Functions
    // ==========================================================================
    function renderIndex(stats, recentLogs) {
        const avgDuration = stats.avg_duration_ms ? (stats.avg_duration_ms / 1000).toFixed(1) + 's' : '-';
        const totalErrors = (stats.error_count || 0) + (stats.timeout_count || 0);
        const totalContent = stats.total_content_length ? (stats.total_content_length / 1000000).toFixed(1) + ' MB' : '0 MB';

        let logsHtml = '';
        if (recentLogs && recentLogs.length > 0) {
            logsHtml = recentLogs.map(log => `
                <tr class="hover:bg-gray-50">
                    <td class="px-6 py-4 whitespace-nowrap">
                        <a href="#" class="log-link text-indigo-600 hover:text-indigo-900 truncate block max-w-xs"
                           data-id="${escapeHtml(log.id)}" title="${escapeHtml(log.url)}">
                            ${escapeHtml(truncateUrl(log.url, 50))}
                        </a>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatDate(log.timestamp)}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${getStatusBadge(log.status)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 uppercase">${escapeHtml(log.content_type)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatDuration(log.duration_ms)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm">
                        <a href="#" class="log-link text-indigo-600 hover:text-indigo-900" data-id="${escapeHtml(log.id)}">Voir</a>
                    </td>
                </tr>
            `).join('');
        } else {
            logsHtml = `
                <tr>
                    <td colspan="6" class="px-6 py-12 text-center text-gray-500">
                        Aucun scrape enregistre pour le moment
                    </td>
                </tr>
            `;
        }

        return `
        <div class="space-y-8">
            <!-- Header -->
            <div class="flex items-center justify-between">
                <h1 class="text-xl font-bold text-gray-900">Dashboard</h1>
                <a href="${API.exportCsv}" class="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition">
                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                    </svg>
                    Export CSV
                </a>
            </div>

            <!-- Stats Cards -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
                    <div class="flex items-center">
                        <div class="p-3 bg-indigo-100 rounded-lg">
                            <svg class="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                            </svg>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm font-medium text-gray-500">Total Scrapes</p>
                            <p class="text-xl font-bold text-gray-900">${stats.total_scrapes || 0}</p>
                        </div>
                    </div>
                </div>

                <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
                    <div class="flex items-center">
                        <div class="p-3 bg-green-100 rounded-lg">
                            <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                            </svg>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm font-medium text-gray-500">Taux de succes</p>
                            <p class="text-xl font-bold text-gray-900">${stats.success_rate || 0}%</p>
                        </div>
                    </div>
                </div>

                <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
                    <div class="flex items-center">
                        <div class="p-3 bg-yellow-100 rounded-lg">
                            <svg class="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                            </svg>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm font-medium text-gray-500">Temps moyen</p>
                            <p class="text-xl font-bold text-gray-900">${avgDuration}</p>
                        </div>
                    </div>
                </div>

                <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
                    <div class="flex items-center">
                        <div class="p-3 bg-red-100 rounded-lg">
                            <svg class="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                      d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                            </svg>
                        </div>
                        <div class="ml-4">
                            <p class="text-sm font-medium text-gray-500">Erreurs</p>
                            <p class="text-xl font-bold text-gray-900">${totalErrors}</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Stats par type -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
                    <h3 class="text-base font-semibold text-gray-900 mb-4">Par type de contenu</h3>
                    <div class="space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="text-gray-600">HTML/SPA</span>
                            <span class="font-semibold text-gray-900">${(stats.html_count || 0) + (stats.spa_count || 0)}</span>
                        </div>
                        <div class="flex items-center justify-between">
                            <span class="text-gray-600">PDF</span>
                            <span class="font-semibold text-gray-900">${stats.pdf_count || 0}</span>
                        </div>
                    </div>
                </div>

                <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
                    <h3 class="text-base font-semibold text-gray-900 mb-4">Par statut</h3>
                    <div class="space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="flex items-center">
                                <span class="w-2 h-2 bg-green-500 rounded-full mr-2"></span>
                                Succes
                            </span>
                            <span class="font-semibold text-green-600">${stats.success_count || 0}</span>
                        </div>
                        <div class="flex items-center justify-between">
                            <span class="flex items-center">
                                <span class="w-2 h-2 bg-red-500 rounded-full mr-2"></span>
                                Erreurs
                            </span>
                            <span class="font-semibold text-red-600">${stats.error_count || 0}</span>
                        </div>
                        <div class="flex items-center justify-between">
                            <span class="flex items-center">
                                <span class="w-2 h-2 bg-yellow-500 rounded-full mr-2"></span>
                                Timeouts
                            </span>
                            <span class="font-semibold text-yellow-600">${stats.timeout_count || 0}</span>
                        </div>
                    </div>
                </div>

                <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
                    <h3 class="text-base font-semibold text-gray-900 mb-4">Volume de donnees</h3>
                    <div class="space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="text-gray-600">Contenu total</span>
                            <span class="font-semibold text-gray-900">${totalContent}</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Recent Scrapes -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-200">
                <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h2 class="text-base font-semibold text-gray-900">Derniers scrapes</h2>
                    <a href="#" id="view-all-logs" class="text-indigo-600 hover:text-indigo-800 text-sm font-medium">
                        Voir tout &rarr;
                    </a>
                </div>

                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">URL</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duree</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                            ${logsHtml}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        `;
    }

    function renderLogs(data) {
        const { logs, total, page, per_page, total_pages } = data;

        let logsHtml = '';
        if (logs && logs.length > 0) {
            logsHtml = logs.map(log => `
                <tr class="hover:bg-gray-50 transition">
                    <td class="px-6 py-4">
                        <a href="#" class="log-link text-indigo-600 hover:text-indigo-900 truncate block max-w-xs"
                           data-id="${escapeHtml(log.id)}" title="${escapeHtml(log.url)}">
                            ${escapeHtml(truncateUrl(log.url, 45))}
                        </a>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatDate(log.timestamp)}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${getStatusBadge(log.status)}</td>
                    <td class="px-6 py-4 whitespace-nowrap">${getTypeBadge(log.content_type)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm ${getHttpStatusClass(log.http_status_code)}">
                        ${log.http_status_code || '-'}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatDuration(log.duration_ms)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatSize(log.content_length)}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                        <a href="#" class="log-link text-indigo-600 hover:text-indigo-900" data-id="${escapeHtml(log.id)}">Voir</a>
                        <button class="rescrape-btn text-gray-600 hover:text-gray-900" data-id="${escapeHtml(log.id)}">Re-scraper</button>
                    </td>
                </tr>
            `).join('');
        } else {
            logsHtml = `
                <tr>
                    <td colspan="8" class="px-6 py-12 text-center text-gray-500">
                        <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                        <p class="mt-2">Aucun resultat trouve</p>
                        <p class="text-sm">Essayez de modifier vos filtres</p>
                    </td>
                </tr>
            `;
        }

        // Pagination
        let paginationHtml = '';
        if (total_pages > 1) {
            let pagesHtml = '';
            for (let p = 1; p <= total_pages; p++) {
                if (p === page) {
                    pagesHtml += `<span class="px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg">${p}</span>`;
                } else if (p === 1 || p === total_pages || (p >= page - 2 && p <= page + 2)) {
                    pagesHtml += `<a href="#" class="page-link px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50" data-page="${p}">${p}</a>`;
                } else if (p === page - 3 || p === page + 3) {
                    pagesHtml += `<span class="px-2 py-2 text-gray-400">...</span>`;
                }
            }

            paginationHtml = `
            <div class="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
                <div class="flex items-center space-x-2">
                    ${page > 1 ? `<a href="#" class="page-link px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50" data-page="${page - 1}">&larr; Precedent</a>` : ''}
                </div>
                <div class="flex items-center space-x-1">${pagesHtml}</div>
                <div class="flex items-center space-x-2">
                    ${page < total_pages ? `<a href="#" class="page-link px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50" data-page="${page + 1}">Suivant &rarr;</a>` : ''}
                </div>
            </div>
            `;
        }

        const exportUrl = `${API.exportCsv}?${$.param({
            ...(currentFilters.status && { status: currentFilters.status }),
            ...(currentFilters.content_type && { content_type: currentFilters.content_type }),
            ...(currentFilters.url_search && { url_search: currentFilters.url_search })
        })}`;

        return `
        <div class="space-y-6">
            <!-- Header -->
            <div class="flex items-center justify-between">
                <h1 class="text-xl font-bold text-gray-900">Historique des scrapes</h1>
                <div class="flex items-center space-x-3">
                    <a href="${exportUrl}" class="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                        </svg>
                        Export CSV
                    </a>
                </div>
            </div>

            <!-- Filters -->
            <div class="bg-white rounded-xl shadow-sm p-6 border border-gray-200">
                <form id="filter-form" class="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div>
                        <label for="search-input" class="block text-sm font-medium text-gray-700 mb-1">Recherche</label>
                        <input type="text" id="search-input" name="search"
                               value="${escapeHtml(currentFilters.search || '')}"
                               placeholder="URL ou contenu..."
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                    <div>
                        <label for="url-search" class="block text-sm font-medium text-gray-700 mb-1">Filtrer par URL</label>
                        <input type="text" id="url-search" name="url_search"
                               value="${escapeHtml(currentFilters.url_search || '')}"
                               placeholder="Contient..."
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                    <div>
                        <label for="status-filter" class="block text-sm font-medium text-gray-700 mb-1">Statut</label>
                        <select id="status-filter" name="status"
                                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
                            <option value="">Tous</option>
                            <option value="success" ${currentFilters.status === 'success' ? 'selected' : ''}>Succes</option>
                            <option value="error" ${currentFilters.status === 'error' ? 'selected' : ''}>Erreur</option>
                            <option value="timeout" ${currentFilters.status === 'timeout' ? 'selected' : ''}>Timeout</option>
                        </select>
                    </div>
                    <div>
                        <label for="type-filter" class="block text-sm font-medium text-gray-700 mb-1">Type</label>
                        <select id="type-filter" name="content_type"
                                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
                            <option value="">Tous</option>
                            <option value="html" ${currentFilters.content_type === 'html' ? 'selected' : ''}>HTML</option>
                            <option value="spa" ${currentFilters.content_type === 'spa' ? 'selected' : ''}>SPA</option>
                            <option value="pdf" ${currentFilters.content_type === 'pdf' ? 'selected' : ''}>PDF</option>
                        </select>
                    </div>
                </form>
            </div>

            <!-- Logs Table -->
            <div class="bg-white rounded-xl shadow-sm border border-gray-200">
                <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-gray-50">
                    <p class="text-sm text-gray-600">
                        <span class="font-medium">${total}</span> resultat${total > 1 ? 's' : ''}
                        ${total > 0 ? ` - Page ${page} sur ${total_pages}` : ''}
                    </p>
                </div>

                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-gray-200">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">URL</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">HTTP</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duree</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Taille</th>
                                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                            </tr>
                        </thead>
                        <tbody class="bg-white divide-y divide-gray-200">
                            ${logsHtml}
                        </tbody>
                    </table>
                </div>

                ${paginationHtml}
            </div>
        </div>
        `;
    }

    function renderLogDetail(log) {
        const statusBanner = {
            success: { bg: 'bg-green-50 border-green-200', icon: 'text-green-600', text: 'text-green-800', msg: 'Scraping reussi' },
            error: { bg: 'bg-red-50 border-red-200', icon: 'text-red-600', text: 'text-red-800', msg: `Erreur: ${log.error_message || 'Erreur inconnue'}` },
            timeout: { bg: 'bg-yellow-50 border-yellow-200', icon: 'text-yellow-600', text: 'text-yellow-800', msg: `Timeout: ${log.error_message || 'Delai depasse'}` }
        };
        const banner = statusBanner[log.status] || statusBanner.error;

        // PDF metadata
        let pdfHtml = '';
        if (log.content_type === 'pdf' && (log.pdf_title || log.pdf_author || log.pdf_pages)) {
            pdfHtml = `
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h2 class="text-base font-semibold text-gray-900 mb-4">Metadonnees PDF</h2>
                <dl class="space-y-3">
                    ${log.pdf_title ? `<div class="flex justify-between"><dt class="text-gray-500">Titre</dt><dd class="text-gray-900">${escapeHtml(log.pdf_title)}</dd></div>` : ''}
                    ${log.pdf_author ? `<div class="flex justify-between"><dt class="text-gray-500">Auteur</dt><dd class="text-gray-900">${escapeHtml(log.pdf_author)}</dd></div>` : ''}
                    ${log.pdf_pages ? `<div class="flex justify-between"><dt class="text-gray-500">Pages</dt><dd class="text-gray-900">${log.pdf_pages}</dd></div>` : ''}
                    ${log.pdf_creation_date ? `<div class="flex justify-between"><dt class="text-gray-500">Date de creation</dt><dd class="text-gray-900">${escapeHtml(log.pdf_creation_date)}</dd></div>` : ''}
                </dl>
            </div>
            `;
        }

        // SSL info
        let sslHtml = '';
        if (log.ssl_info) {
            sslHtml = `
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h2 class="text-base font-semibold text-gray-900 mb-4">Certificat SSL</h2>
                <dl class="space-y-3">
                    ${log.ssl_info.valid !== undefined ? `<div class="flex justify-between"><dt class="text-gray-500">Valide</dt><dd class="${log.ssl_info.valid ? 'text-green-600' : 'text-red-600'}">${log.ssl_info.valid ? 'Oui' : 'Non'}</dd></div>` : ''}
                    ${log.ssl_info.issuer ? `<div class="flex justify-between"><dt class="text-gray-500">Emetteur</dt><dd class="text-gray-900 text-sm">${escapeHtml(log.ssl_info.issuer)}</dd></div>` : ''}
                    ${log.ssl_info.expires ? `<div class="flex justify-between"><dt class="text-gray-500">Expiration</dt><dd class="text-gray-900">${escapeHtml(log.ssl_info.expires)}</dd></div>` : ''}
                </dl>
            </div>
            `;
        }

        // Response headers
        let headersHtml = '';
        if (log.response_headers && Object.keys(log.response_headers).length > 0) {
            const headersText = Object.entries(log.response_headers).map(([k, v]) => `${k}: ${v}`).join('\n');
            headersHtml = `
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h2 class="text-base font-semibold text-gray-900 mb-4">Headers de reponse</h2>
                <div class="bg-gray-50 rounded-lg p-4 overflow-x-auto">
                    <pre class="text-xs text-gray-700 whitespace-pre-wrap">${escapeHtml(headersText)}</pre>
                </div>
            </div>
            `;
        }

        // Redirects
        let redirectsHtml = '';
        if (log.redirects && log.redirects.length > 0) {
            redirectsHtml = `
            <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h2 class="text-base font-semibold text-gray-900 mb-4">Redirections</h2>
                <ul class="space-y-2">
                    ${log.redirects.map(r => `<li class="text-sm text-gray-600 break-all">${escapeHtml(r)}</li>`).join('')}
                </ul>
            </div>
            `;
        }

        // Markdown content
        let markdownHtml = '';
        if (log.markdown_content) {
            markdownHtml = `
            <div class="bg-white rounded-xl shadow-sm border border-gray-200">
                <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h2 class="text-base font-semibold text-gray-900">Contenu Markdown</h2>
                    <button id="copy-markdown" class="text-sm text-indigo-600 hover:text-indigo-800">Copier</button>
                </div>
                <div class="p-6">
                    <div id="markdown-content" class="bg-gray-50 rounded-lg p-4 overflow-x-auto max-h-96 overflow-y-auto">
                        <pre class="text-sm text-gray-700 whitespace-pre-wrap">${escapeHtml(log.markdown_content)}</pre>
                    </div>
                </div>
            </div>
            `;
        }

        return `
        <div class="space-y-6">
            <!-- Header -->
            <div class="space-y-2">
                <!-- Row 1: Back link + Re-scrape button -->
                <div class="flex items-center justify-between">
                    <a href="#" id="back-to-logs" class="text-indigo-600 hover:text-indigo-800 text-sm">
                        &larr; Retour a l'historique
                    </a>
                    <button id="rescrape-detail-btn" data-id="${escapeHtml(log.id)}"
                            class="inline-flex items-center px-3 py-1.5 text-sm bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition">
                        <svg class="w-3.5 h-3.5 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                        </svg>
                        Re-scraper
                    </button>
                </div>
                <!-- Row 2: URL title (compact treeview style) -->
                <h1 class="text-sm font-medium text-gray-900 font-mono truncate py-1 px-2 bg-gray-50 rounded border border-gray-200"
                    title="${escapeHtml(log.url)}">${escapeHtml(log.url)}</h1>
            </div>

            <!-- Status Banner -->
            <div class="${banner.bg} border rounded-xl p-4">
                <div class="flex items-center">
                    <svg class="w-6 h-6 ${banner.icon} mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        ${log.status === 'success' ? '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>' : '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>'}
                    </svg>
                    <span class="${banner.text} font-medium">${escapeHtml(banner.msg)}</span>
                </div>
            </div>

            <!-- Metadata Grid -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <!-- Left Column -->
                <div class="space-y-6">
                    <!-- General Info -->
                    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                        <h2 class="text-base font-semibold text-gray-900 mb-4">Informations generales</h2>
                        <dl class="space-y-3">
                            <div class="flex justify-between">
                                <dt class="text-gray-500">ID</dt>
                                <dd class="text-gray-900 font-mono text-sm">${escapeHtml(log.id)}</dd>
                            </div>
                            <div class="flex justify-between">
                                <dt class="text-gray-500">Date</dt>
                                <dd class="text-gray-900">${formatDate(log.timestamp)}</dd>
                            </div>
                            <div class="flex justify-between">
                                <dt class="text-gray-500">Duree</dt>
                                <dd class="text-gray-900">${formatDuration(log.duration_ms)}</dd>
                            </div>
                            <div class="flex justify-between">
                                <dt class="text-gray-500">Type de contenu</dt>
                                <dd>${getTypeBadge(log.content_type)}</dd>
                            </div>
                            <div class="flex justify-between">
                                <dt class="text-gray-500">Code HTTP</dt>
                                <dd class="${getHttpStatusClass(log.http_status_code)}">${log.http_status_code || '-'}</dd>
                            </div>
                            <div class="flex justify-between">
                                <dt class="text-gray-500">JavaScript execute</dt>
                                <dd class="text-gray-900">${log.js_executed ? 'Oui' : 'Non'}</dd>
                            </div>
                        </dl>
                    </div>

                    <!-- Content Info -->
                    <div class="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                        <h2 class="text-base font-semibold text-gray-900 mb-4">Contenu</h2>
                        <dl class="space-y-3">
                            <div class="flex justify-between">
                                <dt class="text-gray-500">Taille</dt>
                                <dd class="text-gray-900">${formatSize(log.content_length)} caracteres</dd>
                            </div>
                            <div class="flex justify-between">
                                <dt class="text-gray-500">Liens extraits</dt>
                                <dd class="text-gray-900">${log.links_count || 0}</dd>
                            </div>
                            <div class="flex justify-between">
                                <dt class="text-gray-500">Images</dt>
                                <dd class="text-gray-900">${log.images_count || 0}</dd>
                            </div>
                            ${log.content_hash ? `
                            <div class="flex justify-between">
                                <dt class="text-gray-500">Hash SHA256</dt>
                                <dd class="text-gray-900 font-mono text-xs truncate max-w-xs" title="${escapeHtml(log.content_hash)}">
                                    ${escapeHtml(log.content_hash.substring(0, 16))}...
                                </dd>
                            </div>
                            ` : ''}
                        </dl>
                    </div>

                    ${pdfHtml}
                    ${sslHtml}
                </div>

                <!-- Right Column -->
                <div class="space-y-6">
                    ${headersHtml}
                    ${redirectsHtml}
                </div>
            </div>

            ${markdownHtml}
        </div>
        `;
    }

    // ==========================================================================
    // Page Loaders
    // ==========================================================================
    function loadIndex() {
        currentPage = 'index';
        $('#page-title').text('Dashboard | SEO Scraper');
        showLoading();

        $.when(fetchStats(), fetchLogs({ per_page: 10 }))
            .done(function(statsRes, logsRes) {
                const stats = statsRes[0] || statsRes;
                const logsData = logsRes[0] || logsRes;
                $('#content').html(renderIndex(stats, logsData.logs));
                bindEvents();
            })
            .fail(function(err) {
                console.error('Error loading index:', err);
                showNotification('Erreur lors du chargement', 'error');
            })
            .always(hideLoading);
    }

    function loadLogs(filters = {}) {
        currentPage = 'logs';
        $('#page-title').text('Historique | SEO Scraper');
        Object.assign(currentFilters, filters);
        showLoading();

        fetchLogs(currentFilters)
            .done(function(data) {
                $('#content').html(renderLogs(data));
                bindEvents();
            })
            .fail(function(err) {
                console.error('Error loading logs:', err);
                showNotification('Erreur lors du chargement', 'error');
            })
            .always(hideLoading);
    }

    function loadLogDetail(id) {
        currentPage = 'detail';
        $('#page-title').text('Detail | SEO Scraper');
        showLoading();

        fetchLog(id)
            .done(function(data) {
                $('#content').html(renderLogDetail(data));
                bindEvents();
            })
            .fail(function(err) {
                console.error('Error loading log detail:', err);
                showNotification('Log non trouve', 'error');
                loadLogs();
            })
            .always(hideLoading);
    }

    // ==========================================================================
    // Event Bindings
    // ==========================================================================
    function bindEvents() {
        // Log links
        $(document).off('click', '.log-link').on('click', '.log-link', function(e) {
            e.preventDefault();
            const id = $(this).data('id');
            if (id) {
                window.history.pushState({}, '', `/dashboard/logs/${id}`);
                loadLogDetail(id);
            }
        });

        // View all logs
        $('#view-all-logs').off('click').on('click', function(e) {
            e.preventDefault();
            window.history.pushState({}, '', '/dashboard/logs');
            loadLogs({ page: 1 });
        });

        // Back to logs
        $('#back-to-logs').off('click').on('click', function(e) {
            e.preventDefault();
            window.history.pushState({}, '', '/dashboard/logs');
            loadLogs();
        });

        // Pagination
        $(document).off('click', '.page-link').on('click', '.page-link', function(e) {
            e.preventDefault();
            const page = $(this).data('page');
            currentFilters.page = page;
            window.history.pushState({}, '', `/dashboard/logs?page=${page}`);
            loadLogs(currentFilters);
        });

        // Filters
        let filterTimeout;
        $('#filter-form').off('change input').on('change', 'select', function() {
            currentFilters.status = $('#status-filter').val();
            currentFilters.content_type = $('#type-filter').val();
            currentFilters.page = 1;
            loadLogs(currentFilters);
        }).on('input', 'input', function() {
            clearTimeout(filterTimeout);
            filterTimeout = setTimeout(function() {
                currentFilters.search = $('#search-input').val();
                currentFilters.url_search = $('#url-search').val();
                currentFilters.page = 1;
                loadLogs(currentFilters);
            }, 500);
        });

        // Rescrape buttons
        $(document).off('click', '.rescrape-btn, #rescrape-detail-btn').on('click', '.rescrape-btn, #rescrape-detail-btn', function() {
            const id = $(this).data('id');
            const $btn = $(this);
            $btn.prop('disabled', true).addClass('opacity-50');

            rescrape(id)
                .done(function() {
                    showNotification('Re-scraping lance avec succes', 'success');
                    setTimeout(function() {
                        if (currentPage === 'detail') {
                            loadLogDetail(id);
                        } else {
                            loadLogs(currentFilters);
                        }
                    }, 2000);
                })
                .fail(function(err) {
                    console.error('Rescrape error:', err);
                    showNotification('Erreur lors du re-scraping', 'error');
                })
                .always(function() {
                    $btn.prop('disabled', false).removeClass('opacity-50');
                });
        });

        // Copy markdown
        $('#copy-markdown').off('click').on('click', function() {
            const content = $('#markdown-content').text();
            navigator.clipboard.writeText(content).then(function() {
                showNotification('Contenu copie !', 'success');
            }).catch(function() {
                showNotification('Erreur lors de la copie', 'error');
            });
        });
    }

    // ==========================================================================
    // Router
    // ==========================================================================
    function router() {
        const path = window.location.pathname;
        const match = path.match(/^\/dashboard\/logs\/([^/]+)$/);

        if (match) {
            loadLogDetail(match[1]);
        } else if (path === '/dashboard/logs' || path === '/dashboard/logs/') {
            // Parse query params
            const params = new URLSearchParams(window.location.search);
            currentFilters.page = parseInt(params.get('page')) || 1;
            currentFilters.status = params.get('status') || '';
            currentFilters.content_type = params.get('content_type') || '';
            currentFilters.url_search = params.get('url_search') || '';
            currentFilters.search = params.get('search') || '';
            loadLogs(currentFilters);
        } else {
            loadIndex();
        }
    }

    // ==========================================================================
    // Navigation
    // ==========================================================================
    $(document).on('click', '#nav-dashboard', function(e) {
        e.preventDefault();
        window.history.pushState({}, '', '/dashboard/');
        loadIndex();
    });

    $(document).on('click', '#nav-logs', function(e) {
        e.preventDefault();
        window.history.pushState({}, '', '/dashboard/logs');
        currentFilters = { page: 1, per_page: 20, status: '', content_type: '', url_search: '', search: '' };
        loadLogs();
    });

    // Handle browser back/forward
    $(window).on('popstate', router);

    // Keyboard shortcuts
    $(document).on('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const $search = $('#search-input');
            if ($search.length) {
                $search.focus().select();
            }
        }
    });

    // ==========================================================================
    // Init
    // ==========================================================================
    $(document).ready(function() {
        router();
    });

    // Export for global use
    window.showNotification = showNotification;

})(jQuery);
