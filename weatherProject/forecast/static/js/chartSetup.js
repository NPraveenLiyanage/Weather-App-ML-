document.addEventListener('DOMContentLoaded', () => {
    const chartElement = document.getElementById('chart');
    if (!chartElement) {
        console.log('Canvas Element not found!');
        return;
    }

    const ctx = chartElement.getContext('2d');
    const gradient = ctx.createLinearGradient(0, -10, 0, 100);
    gradient.addColorStop(0, 'rgba(250, 0, 0, 1)');
    gradient.addColorStop(1, 'rgba(136, 255, 0, 1)');

    const forecastItems = document.querySelectorAll('.forecast_item');

    const temps = [];
    const times = [];

    forecastItems.forEach(item => {
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
    console.debug('chartSetup: forecastItems count =', forecastItems.length);
    console.debug('chartSetup: times =', times);
    console.debug('chartSetup: temps =', temps);

    // Only run chart if at least one forecast item and all have valid data
    if (forecastItems.length === 0 || temps.length === 0 || times.length === 0) {
    return;
    }
    if (temps.length !== forecastItems.length || times.length !== forecastItems.length) {
        // Do not log error, just skip chart rendering if any item is missing data
        return;
    }

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: times,
            datasets: [
                {
                    label:'Celsius Degrees',
                    data: temps,
                    borderColor: gradient,
                    borderWidth: 2,
                    tension: 0.4,
                    pointRadius: 2,
                },
            ],
        },
        options:{
            plugins: {
                legend: {
                    display: false,
                },
            },
            scales:{
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
});