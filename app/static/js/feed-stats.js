/**
 * feed-stats.js
 * Feed Stats Enhancement v1.0
 * Renders the Platform Activity card + 14-day trend line chart at bottom of homepage feed.
 * Expects window.feedStats = { total_views, today, week, month, daily_views: [{date, count}, ...] }
 * Chart.js 4+ must be loaded before this script (CDN in template).
 * Graceful: does nothing if elements or data missing.
 */
(function () {
    function initFeedStats() {
        const canvas = document.getElementById('viewsTrendChart');
        if (!canvas || typeof Chart === 'undefined') {
            return; // no chart element or library not ready
        }

        const stats = window.feedStats || {};
        const daily = Array.isArray(stats.daily_views) ? stats.daily_views : [];

        // Update numeric values (defensive sync in case template numbers lag)
        const setNum = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = (val || 0).toLocaleString();
        };
        setNum('stat-total', stats.total_views);
        setNum('stat-today', stats.today);
        setNum('stat-week', stats.week);
        setNum('stat-month', stats.month);

        if (daily.length === 0) {
            // No data yet (or first run) — still render empty chart nicely
            // Destroy previous if hot reload in dev
            if (canvas._chartInstance) {
                try { canvas._chartInstance.destroy(); } catch (e) {}
            }
            const ctxEmpty = canvas.getContext('2d');
            new Chart(ctxEmpty, {
                type: 'line',
                data: {
                    labels: ['No data yet'],
                    datasets: [{
                        label: 'Daily Views',
                        data: [0],
                        borderColor: '#8B4513',
                        backgroundColor: 'rgba(139, 69, 19, 0.08)',
                        borderWidth: 2,
                        tension: 0.35,
                        fill: true,
                        pointRadius: 2
                    }]
                },
                options: getChartOptions()
            });
            return;
        }

        // Prepare labels (short readable dates e.g. "Jun 20") and values
        const labels = daily.map(d => {
            try {
                const dt = new Date(d.date + 'T00:00:00Z');
                return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            } catch (_) {
                return d.date.slice(5); // fallback MM-DD
            }
        });
        const values = daily.map(d => Number(d.count) || 0);

        // Destroy stale chart instance (dev / re-init safety)
        if (canvas._chartInstance) {
            try { canvas._chartInstance.destroy(); } catch (e) {}
        }

        const ctx = canvas.getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Daily Views',
                    data: values,
                    borderColor: '#8B4513',           // primary terracotta
                    backgroundColor: 'rgba(139, 69, 19, 0.10)',
                    borderWidth: 2.5,
                    tension: 0.35,
                    fill: true,
                    pointRadius: 2.5,
                    pointHoverRadius: 4,
                    pointBackgroundColor: '#8B4513'
                }]
            },
            options: getChartOptions(values)
        });

        // Store for potential future destroy / access
        canvas._chartInstance = chart;
    }

    function getChartOptions(values) {
        const maxVal = values && values.length ? Math.max.apply(null, values) : 10;
        const suggestedMax = Math.max(5, Math.ceil(maxVal * 1.25));

        return {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: '#F0E9DF', lineWidth: 0.5, tickLength: 3 },
                    ticks: {
                        color: '#6B6259',
                        font: { size: 10 },
                        maxRotation: 45,
                        autoSkip: true,
                        maxTicksLimit: 8
                    }
                },
                y: {
                    beginAtZero: true,
                    suggestedMax: suggestedMax,
                    grid: { color: '#F0E9DF', lineWidth: 0.5 },
                    ticks: {
                        color: '#6B6259',
                        font: { size: 10 },
                        precision: 0,
                        stepSize: Math.max(1, Math.ceil(suggestedMax / 5))
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    displayColors: false,
                    callbacks: {
                        label: (ctx) => `${ctx.raw} view${ctx.raw === 1 ? '' : 's'}`
                    }
                }
            },
            elements: {
                line: { borderJoinStyle: 'round' },
                point: { hitRadius: 8 }
            },
            animation: {
                duration: 650,
                easing: 'easeOutQuart'
            }
        };
    }

    // Auto-init when DOM ready (works whether script is at end or deferred)
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFeedStats);
    } else {
        // DOM already parsed
        // Small delay allows other homepage JS (listings) to settle
        setTimeout(initFeedStats, 40);
    }

    // Also expose for manual re-init if needed (e.g. future dynamic refresh)
    window.initFeedStats = initFeedStats;
})();