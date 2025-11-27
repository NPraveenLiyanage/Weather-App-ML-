(function () {
    const renderForecastChart = () => {
        const chartElement = document.getElementById('chart');
        if (!chartElement) {
            return;
        }

        const forecastItems = document.querySelectorAll('.forecast_item');
        if (!forecastItems.length) {
            if (window.forecastChartInstance) {
                window.forecastChartInstance.destroy();
                window.forecastChartInstance = null;
            }
            return;
        }

        const temps = [];
        const times = [];

        forecastItems.forEach((item) => {
            const timeEl = item.querySelector('.forecast-time');
            const tempEl = item.querySelector('.forecast-temperatureValue');
            const humEl = item.querySelector('.forecast-humidityValue');
            if (!timeEl || !tempEl || !humEl) {
                return;
            }
            const time = timeEl.textContent.trim();
            const temp = parseFloat(tempEl.textContent.trim());
            const hum = humEl.textContent.trim();
            if (time && !Number.isNaN(temp) && hum) {
                times.push(time);
                temps.push(temp);
            }
        });

        const MAX_POINTS = 5;
        if (times.length > MAX_POINTS) {
            times.splice(MAX_POINTS);
            temps.splice(MAX_POINTS);
        }

        if (!temps.length || temps.length !== times.length) {
            if (window.forecastChartInstance) {
                window.forecastChartInstance.destroy();
                window.forecastChartInstance = null;
            }
            return;
        }

        if (window.forecastChartInstance) {
            window.forecastChartInstance.destroy();
        }

        const ctx = chartElement.getContext('2d');
        const accentColor = '#ffb347';
        const glowColor = 'rgba(255, 179, 71, 0.6)';

        window.forecastChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: times,
                datasets: [
                    {
                        label: 'Celsius Degrees',
                        data: temps,
                        borderColor: accentColor,
                        borderWidth: 3,
                        tension: 0.35,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHitRadius: 10,
                        fill: false,
                    },
                ],
            },
            options: {
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => `${context.parsed.y}°C`,
                        },
                    },
                },
                maintainAspectRatio: false,
                elements: {
                    line: {
                        borderJoinStyle: 'round',
                        borderCapStyle: 'round',
                        shadowColor: glowColor,
                        shadowBlur: 12,
                        shadowOffsetX: 0,
                        shadowOffsetY: 0,
                    },
                },
                scales: {
                    x: {
                        display: false,
                        grid: {
                            drawOnChartArea: false,
                        },
                    },
                    y: {
                        display: false,
                        grid: {
                            drawOnChartArea: false,
                        },
                    },
                },
                animation: {
                    duration: 600,
                },
            },
        });
    };

    window.renderForecastChart = renderForecastChart;
    document.addEventListener('DOMContentLoaded', renderForecastChart);
})();