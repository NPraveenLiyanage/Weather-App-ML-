document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('form[data-auto-url]');
    const main = document.querySelector('main[data-fallback-city]');
    const overlay = document.getElementById('loading-overlay');
    const statusBanner = document.getElementById('status-banner');
    const locationInput = document.querySelector('.geo-input');
    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    const favoritesListEl = document.querySelector('.favorites-list');
    const saveFavoriteBtn = document.querySelector('.btn-save-favorite');
    const rainAlertToggle = document.querySelector('.input-rain-alert');
    const tempThresholdInput = document.querySelector('.input-temp-threshold');
    const settingsToggle = document.querySelector('.settings-toggle');
    const personalizationDrawer = document.getElementById('personalization-drawer');
    const drawerCloseBtn = document.querySelector('.drawer-close');
    const bookmarkTrigger = document.querySelector('.bookmark-trigger');
    const drawerOverlay = document.getElementById('drawer-overlay');

    if (!form || !main || !csrfInput) {
        return;
    }

    const autoUrl = form.dataset.autoUrl;
    const fallbackCity = main.dataset.fallbackCity || 'Colombo';
    const baseClasses = main.dataset.baseClasses || main.className;
    const hasInitialData = main.dataset.hasInitial === 'true';
    const STORAGE_KEY = 'weather:last-context';
    const FAVORITES_KEY = 'weather:favorites';
    const ALERTS_KEY = 'weather:alerts';
    let latestContext = null;
    let toastTimer = null;

    const showStatus = (message, variant = 'info', options = {}) => {
        if (!statusBanner) {
            return;
        }
        statusBanner.textContent = message;
        statusBanner.classList.remove('visually-hidden', 'info', 'error', 'success');
        statusBanner.classList.add(variant);
        if (toastTimer) {
            window.clearTimeout(toastTimer);
            toastTimer = null;
        }
        if (!options.persistent) {
            const duration = options.duration ?? (variant === 'error' ? 6000 : 4000);
            toastTimer = window.setTimeout(() => {
                if (statusBanner.textContent === message) {
                    clearStatus();
                }
            }, duration);
        }
    };

    const clearStatus = () => {
        if (!statusBanner) {
            return;
        }
        statusBanner.textContent = '';
        statusBanner.classList.add('visually-hidden');
        statusBanner.classList.remove('info', 'error', 'success');
        if (toastTimer) {
            window.clearTimeout(toastTimer);
            toastTimer = null;
        }
    };

    const markLoading = () => {
        if (main.classList.contains('ready')) {
            return;
        }
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

    const safeValue = (value, fallback = '--') => {
        if (value === null || value === undefined || value === '') {
            return fallback;
        }
        return value;
    };

    const formatDateTime = (value) => {
        if (!value) {
            return '--';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }
        return parsed.toLocaleString();
    };

    const loadCachedContext = () => {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (error) {
            console.debug('Unable to read cached context', error);
            return null;
        }
    };

    const saveCachedContext = (data) => {
        if (!data) {
            return;
        }
        try {
            const payload = {
                ...data,
                cachedAt: data.updated_at || new Date().toISOString(),
            };
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
        } catch (error) {
            console.debug('Unable to cache context', error);
        }
    };

    const loadFavorites = () => {
        try {
            const raw = window.localStorage.getItem(FAVORITES_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (error) {
            console.debug('Unable to load favorites', error);
            return [];
        }
    };

    const saveFavorites = (items) => {
        try {
            window.localStorage.setItem(FAVORITES_KEY, JSON.stringify(items));
        } catch (error) {
            console.debug('Unable to save favorites', error);
        }
    };

    const renderFavorites = () => {
        if (!favoritesListEl) {
            return;
        }
        const favorites = loadFavorites();
        favoritesListEl.innerHTML = '';
        if (!favorites.length) {
            const emptyText = favoritesListEl.dataset.emptyText || 'No favorites yet';
            const li = document.createElement('li');
            li.className = 'text-white-50';
            li.textContent = emptyText;
            favoritesListEl.appendChild(li);
            return;
        }
        favorites.forEach((fav) => {
            const li = document.createElement('li');
            const selectBtn = document.createElement('button');
            selectBtn.className = 'favorite-select';
            selectBtn.type = 'button';
            selectBtn.dataset.city = fav.city;
            selectBtn.textContent = fav.country ? `${fav.city}, ${fav.country}` : fav.city;

            const removeBtn = document.createElement('button');
            removeBtn.className = 'favorite-remove';
            removeBtn.type = 'button';
            removeBtn.dataset.city = fav.city;
            removeBtn.setAttribute('aria-label', `Remove ${fav.city}`);
            removeBtn.textContent = '✕';

            li.appendChild(selectBtn);
            li.appendChild(removeBtn);
            favoritesListEl.appendChild(li);
        });
    };

    const loadAlerts = () => {
        try {
            const raw = window.localStorage.getItem(ALERTS_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch (error) {
            console.debug('Unable to load alerts', error);
            return {};
        }
    };

    const saveAlerts = (settings) => {
        try {
            window.localStorage.setItem(ALERTS_KEY, JSON.stringify(settings));
        } catch (error) {
            console.debug('Unable to save alerts', error);
        }
    };

    const syncAlertInputs = () => {
        const settings = loadAlerts();
        if (rainAlertToggle) {
            rainAlertToggle.checked = Boolean(settings.rainAlert);
        }
        if (tempThresholdInput) {
            tempThresholdInput.value = settings.tempAlertValue ?? '';
        }
    };

    const requestNotificationPermission = () => {
        if (!('Notification' in window)) {
            return;
        }
        if (Notification.permission === 'default') {
            Notification.requestPermission();
        }
    };

    const sendBrowserNotification = (message) => {
        if (!('Notification' in window)) {
            return;
        }
        if (Notification.permission === 'granted') {
            try {
                new Notification('Weather Alert', { body: message });
            } catch (error) {
                console.debug('Unable to show notification', error);
            }
        }
    };

    const evaluateAlerts = (data) => {
        if (!data) {
            return;
        }
        const settings = loadAlerts();
        const messages = [];

        if (settings.rainAlert && data.rain_outlook && data.rain_outlook.toLowerCase().includes('likely')) {
            messages.push(`Rain likely soon in ${data.city}.`);
        }

        const maxTemp = parseFloat(data.MaxTemp);
        if (settings.tempAlertValue && !Number.isNaN(maxTemp) && maxTemp >= Number(settings.tempAlertValue)) {
            messages.push(`High temperature alert: up to ${data.MaxTemp}°C.`);
        }

        if (messages.length) {
            const combined = messages.join(' ');
            showStatus(combined, 'success');
            sendBrowserNotification(combined);
        }
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
                <p class="forecastDescription">${safeValue(item.description, '')}</p>
            `;
            list.appendChild(li);
        });
    };

    const applyWeatherContext = (data, { fromCache = false } = {}) => {
        if (!data) {
            return;
        }
        latestContext = data;
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
        setText('.sunrise-value', data.sunrise);
        setText('.sunset-value', data.sunset);
        setText('.rain-outlook-value', data.rain_outlook);

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

        if (!fromCache) {
            saveCachedContext(data);
            clearStatus();
        }

        evaluateAlerts(data);
        markLoaded();
    };

    const fetchWeather = (payload = {}, { skipLoading = false } = {}) => {
        if (!autoUrl) {
            return Promise.resolve();
        }
        if (!skipLoading) {
            markLoading();
        }
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
                showStatus('Unable to fetch the latest weather. Showing saved data if available.', 'error');
                markLoaded();
            });
    };

    const hydrateContextFromDom = () => {
        const city = document.querySelector('.weather__location-city')?.textContent?.trim();
        if (!city) {
            return;
        }
        const country = document.querySelector('.weather__location-country')?.textContent?.trim() || '';
        latestContext = {
            city,
            country,
        };
    };

    hydrateContextFromDom();

    const serverErrorMessage = main.dataset.serverError?.trim();
    if (serverErrorMessage) {
        showStatus(serverErrorMessage, 'error');
    }

    let geolocationResolved = false;
    let fallbackRequested = false;
    let fallbackTimer = null;
    let triggerFallback = () => {};

    if (hasInitialData) {
        markLoaded();
    } else {
        const cachedContext = loadCachedContext();
        if (cachedContext) {
            applyWeatherContext(cachedContext, { fromCache: true });
            const when = cachedContext.cachedAt ? formatDateTime(cachedContext.cachedAt) : 'earlier';
            showStatus(`Showing saved forecast from ${when} while we fetch fresh data.`, 'info');
        }

        triggerFallback = (force = false) => {
            if (fallbackRequested && !force) {
                return;
            }
            fallbackRequested = true;
            fetchWeather({ fallback_city: fallbackCity }).finally(() => {
                fallbackRequested = false;
            });
        };

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
    }

    window.addEventListener('offline', () => {
        showStatus('You appear to be offline. Showing saved forecast.', 'error', { persistent: true });
    });

    window.addEventListener('online', () => {
        clearStatus();
        if (!hasInitialData) {
            triggerFallback(true);
        }
    });

    renderFavorites();
    syncAlertInputs();

    const handleSaveFavorite = () => {
        if (!latestContext || !latestContext.city) {
            showStatus('No city data to save yet.', 'error');
            return;
        }
        const favorites = loadFavorites();
        const exists = favorites.some((fav) => fav.city.toLowerCase() === latestContext.city.toLowerCase());
        if (exists) {
            showStatus('City already in favorites.', 'info');
            return;
        }
        const nextFavorites = [{ city: latestContext.city, country: latestContext.country }, ...favorites].slice(0, 10);
        saveFavorites(nextFavorites);
        renderFavorites();
        showStatus(`${latestContext.city} saved to favorites.`, 'success');
    };

    if (saveFavoriteBtn) {
        saveFavoriteBtn.addEventListener('click', handleSaveFavorite);
    }

    if (bookmarkTrigger) {
        bookmarkTrigger.addEventListener('click', handleSaveFavorite);
    }

    if (favoritesListEl) {
        favoritesListEl.addEventListener('click', (event) => {
            const target = event.target;
            if (target.matches('.favorite-select')) {
                const city = target.dataset.city;
                if (city) {
                    fetchWeather({ city });
                }
            }
            if (target.matches('.favorite-remove')) {
                const city = target.dataset.city;
                const favorites = loadFavorites().filter((fav) => fav.city !== city);
                saveFavorites(favorites);
                renderFavorites();
            }
        });
    }

    if (rainAlertToggle) {
        rainAlertToggle.addEventListener('change', () => {
            const settings = loadAlerts();
            settings.rainAlert = rainAlertToggle.checked;
            saveAlerts(settings);
            if (rainAlertToggle.checked) {
                requestNotificationPermission();
                showStatus('Rain alerts enabled.', 'success');
            }
        });
    }

    if (tempThresholdInput) {
        tempThresholdInput.addEventListener('change', () => {
            const value = tempThresholdInput.value;
            const settings = loadAlerts();
            settings.tempAlertValue = value ? Number(value) : '';
            saveAlerts(settings);
            if (value) {
                showStatus(`High temperature alert set to ${value}°C.`, 'success');
            }
        });
    }

    const updateDrawerState = (open) => {
        if (!personalizationDrawer || !settingsToggle) {
            return;
        }
        personalizationDrawer.classList.toggle('open', open);
        personalizationDrawer.setAttribute('aria-hidden', open ? 'false' : 'true');
        settingsToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (drawerOverlay) {
            drawerOverlay.classList.toggle('active', open);
            drawerOverlay.setAttribute('aria-hidden', open ? 'false' : 'true');
        }
        document.body.classList.toggle('drawer-open', open);
    };

    const isDrawerOpen = () => personalizationDrawer?.classList.contains('open');

    if (settingsToggle && personalizationDrawer) {
        settingsToggle.addEventListener('click', (event) => {
            event.stopPropagation();
            updateDrawerState(!isDrawerOpen());
        });

        drawerCloseBtn?.addEventListener('click', () => updateDrawerState(false));
        drawerOverlay?.addEventListener('click', () => updateDrawerState(false));

        document.addEventListener('click', (event) => {
            if (!isDrawerOpen()) {
                return;
            }
            if (personalizationDrawer.contains(event.target) || settingsToggle.contains(event.target)) {
                return;
            }
            updateDrawerState(false);
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && isDrawerOpen()) {
                updateDrawerState(false);
            }
        });
    }
});
