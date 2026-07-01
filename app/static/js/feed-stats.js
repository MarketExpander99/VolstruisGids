/**
 * feed-stats.js
 * Feed Stats Enhancement v1.1
 * Platform Activity card + 30-day bar chart at bottom of feed (replaces simple hit counter).
 * Expects window.feedStats = { total_views, today, week, month, daily_views: [{date, count}, ...] }
 * Chart.js 4+ via CDN. Supports demo sample data. ARIA + labels present in template.
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
                type: 'bar',
                data: {
                    labels: ['No data yet'],
                    datasets: [{
                        label: 'Daily Views',
                        data: [0],
                        backgroundColor: 'rgba(139, 69, 19, 0.5)',
                        borderColor: '#8B4513',
                        borderWidth: 1,
                        barPercentage: 0.6
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
        const isDense = values.length > 20;
        const chart = new Chart(ctx, {
            type: 'bar',  // bar graph shows each of the 30 days more distinctly
            data: {
                labels: labels,
                datasets: [{
                    label: 'Daily Views',
                    data: values,
                    backgroundColor: 'rgba(139, 69, 19, 0.7)',
                    borderColor: '#8B4513',
                    borderWidth: 1,
                    barPercentage: isDense ? 0.65 : 0.85,
                    categoryPercentage: 0.9
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
                        maxTicksLimit: 12  // show more labels so the 30-day range is clearer
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