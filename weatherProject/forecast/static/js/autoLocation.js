document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('form[data-auto-url]');
    const locationInput = document.querySelector('.geo-input');
    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');

    if (!form || !locationInput || !csrfInput) {
        return;
    }

    const autoUrl = form.dataset.autoUrl;
    const hasLocation = locationInput.value && locationInput.value.trim().length > 0;

    if (!autoUrl || hasLocation || !('geolocation' in navigator)) {
        return;
    }

    const submitDefaultLocation = (coords) => {
        fetch(autoUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfInput.value,
            },
            body: JSON.stringify({
                lat: coords.latitude,
                lon: coords.longitude,
            }),
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error('Auto location request failed');
                }
                return response.json();
            })
            .then((data) => {
                if (data && data.city && !locationInput.value.trim()) {
                    locationInput.value = data.city;
                    form.submit();
                }
            })
            .catch((error) => {
                console.debug('Unable to set the default location', error);
            });
    };

    navigator.geolocation.getCurrentPosition(
        (position) => submitDefaultLocation(position.coords),
        (error) => console.debug('Geolocation not available', error),
        {
            enableHighAccuracy: false,
            timeout: 10000,
            maximumAge: 300000,
        },
    );
});
