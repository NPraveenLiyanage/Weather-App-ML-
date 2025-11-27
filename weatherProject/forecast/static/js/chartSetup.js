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
            const temp = tempEl.textContent.trim();
            const hum = humEl.textContent.trim();
            if (time && temp && hum) {
                times.push(time);
                temps.push(temp);
            }
        });

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
        const gradient = ctx.createLinearGradient(0, -10, 0, 100);
        gradient.addColorStop(0, 'rgba(250, 0, 0, 1)');
        gradient.addColorStop(1, 'rgba(136, 255, 0, 1)');

        window.forecastChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: times,
                datasets: [
                    {
                        label: 'Celsius Degrees',
                        data: temps,
                        borderColor: gradient,
                        borderWidth: 2,
                        tension: 0.4,
                        pointRadius: 2,
                    },
                ],
            },
            options: {
                plugins: {
                    legend: {
                        display: false,
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
                    duration: 750,
                },
            },
        });
    };

    window.renderForecastChart = renderForecastChart;
    document.addEventListener('DOMContentLoaded', renderForecastChart);
})();