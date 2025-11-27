document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('form[data-auto-url]');
    const main = document.querySelector('main[data-fallback-city]');
    const overlay = document.getElementById('loading-overlay');
    const locationInput = document.querySelector('.geo-input');
    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');

    if (!form || !main || !csrfInput) {
        return;
    }

    const autoUrl = form.dataset.autoUrl;
    const fallbackCity = main.dataset.fallbackCity || 'Colombo';
    const baseClasses = main.dataset.baseClasses || main.className;
    const hasInitialData = main.dataset.hasInitial === 'true';

    const markLoading = () => {
        overlay?.classList.add('active');
        overlay?.classList.remove('hidden');
        main.classList.add('loading-state');
        main.classList.remove('ready');
    };

    const markLoaded = () => {
        main.classList.remove('loading-state');
        main.classList.add('ready');
        overlay?.classList.remove('active');
        overlay?.classList.add('hidden');
    };

    if (hasInitialData) {
        markLoaded();
        return;
    }

    const safeValue = (value, fallback = '--') => {
        if (value === null || value === undefined || value === '') {
            return fallback;
        }
        return value;
    };

    const setText = (selector, value) => {
        const el = document.querySelector(selector);
        if (el) {
            el.textContent = safeValue(value);
        }
    };

    const updateForecastList = (forecast = []) => {
        const list = document.querySelector('.forecast');
        if (!list) {
            return;
        }
        list.innerHTML = '';

        if (!forecast.length) {
            const placeholder = document.createElement('li');
            placeholder.className = 'forecast_placeholder text-white-50';
            placeholder.textContent = 'Forecast data will appear here.';
            list.appendChild(placeholder);
            return;
        }

        forecast.forEach((item) => {
            const li = document.createElement('li');
            li.className = 'forecast_item';
            li.innerHTML = `
                <p class="forecast-time">${safeValue(item.time, '--:--')}</p>
                <p class="forecast-temperature">
                    &nbsp;<span class="forecast-temperatureValue">${safeValue(item.temp)}</span>°
                </p>
                <p class="forecastWindText">
                    Humidity: <span class="forecast-humidityValue">${safeValue(item.humidity)}</span>
                </p>
            `;
            list.appendChild(li);
        });
    };

    const applyWeatherContext = (data) => {
        if (!data) {
            return;
        }
        if (locationInput && data.location) {
            locationInput.value = data.location;
        }
        setText('.day-stats__temperature_value', data.current_temp);
        setText('.day-stats__feelslike_value', data.feels_like);
        setText('.day-stats__humidity', data.humidity);
        setText('.day-stats__clouds', data.clouds);
        setText('.weather__primary-title', data.description || 'Weather Forecast');
        setText('.weather__location-city', data.city);
        setText('.weather__location-country', data.country);
        setText('.weather__location-date', data.time);
        setText('.weatherWindKph', data.wind);
        setText('.weatherPressure', data.pressure);
        setText('.weatherSnow', data.visibility);
        setText('.weatherMaxTemp', data.MaxTemp);
        setText('.weatherMinTemp', data.MinTemp);

        const mainElement = main;
        if (mainElement && baseClasses) {
            mainElement.className = baseClasses;
            if (data.description_class) {
                mainElement.classList.add(data.description_class);
            }
            mainElement.classList.remove('loading-state');
            mainElement.classList.add('ready');
        }

        updateForecastList(data.forecast || []);

        if (window.renderForecastChart) {
            window.renderForecastChart();
        }

        markLoaded();
    };

    const fetchWeather = (payload) => {
        if (!autoUrl) {
            return Promise.resolve();
        }
        markLoading();
        return fetch(autoUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfInput.value,
            },
            body: JSON.stringify(payload),
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error('Auto weather request failed');
                }
                return response.json();
            })
            .then((data) => applyWeatherContext(data))
            .catch((error) => {
                console.debug('Auto weather request failed', error);
                markLoaded();
            });
    };

    let geolocationResolved = false;
    let fallbackRequested = false;

    const triggerFallback = () => {
        if (fallbackRequested) {
            return;
        }
        fallbackRequested = true;
        fetchWeather({ fallback_city: fallbackCity });
    };

    let fallbackTimer = null;
    const startFallbackTimer = () => {
        fallbackTimer = setTimeout(() => {
            if (!geolocationResolved) {
                triggerFallback();
            }
        }, 6000);
    };

    if ('geolocation' in navigator) {
        startFallbackTimer();
        navigator.geolocation.getCurrentPosition(
            (position) => {
                geolocationResolved = true;
                if (fallbackTimer) {
                    clearTimeout(fallbackTimer);
                }
                fetchWeather({
                    lat: position.coords.latitude,
                    lon: position.coords.longitude,
                });
            },
            (error) => {
                console.debug('Geolocation not available', error);
                if (fallbackTimer) {
                    clearTimeout(fallbackTimer);
                }
                triggerFallback();
            },
            {
                enableHighAccuracy: false,
                timeout: 8000,
                maximumAge: 300000,
            },
        );
    } else {
        triggerFallback();
    }
});
