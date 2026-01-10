import json

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST

# Create your views here.

import requests #this lib help us to fetch data from API
import pandas as pd #for handling and analyzing data 
import numpy as np #for numerical operations
from sklearn.model_selection import train_test_split #to split data into training and testing
from sklearn.preprocessing import LabelEncoder #to convert categorical data into numerical values
from sklearn.ensemble import RandomForestClassifier #to build a random forest classification model
from sklearn.metrics import mean_squared_error #to measure the accuracy of our predictions
from datetime import datetime #to work with dates and times
import pytz
import os
import logging

API_Key = os.environ.get('OPENWEATHER_API_KEY')
# In development, allow a fallback if DEBUG is enabled to ease local testing
if not API_Key:
    try:
        from weatherProject import settings as _settings
        if getattr(_settings, 'DEBUG', True):
            # allow a developer to set OPENWEATHER_API_KEY in their local env or .env file
            API_Key = os.environ.get('OPENWEATHER_API_KEY')
    except Exception:
        # If settings can't be imported, leave API_Key as None
        pass
BASE_URL = 'https://api.openweathermap.org/data/2.5/'
DEFAULT_CITY = os.environ.get('DEFAULT_CITY', 'Colombo')


#Fetch current weather data

def _serialize_weather(data):
    return {
        'city': data['name'],
        'current_temp': round(data['main']['temp']),
        'feels_like': round(data['main']['feels_like']),
        'temp_min': round(data['main']['temp_min']),
        'temp_max': round(data['main']['temp_max']),
        'humidity': round(data['main']['humidity']),
        'description': data['weather'][0]['description'],
        'country': data['sys']['country'],
        'wind_gust_dir': data['wind']['deg'],
        'pressure': data['main']['pressure'],
        'wind_gust_speed': data['wind']['speed'],
        'clouds': data['clouds']['all'],
        'Visibility': data.get('visibility', 0),
        'lat': data['coord']['lat'],
        'lon': data['coord']['lon'],
        'sunrise': data['sys'].get('sunrise'),
        'sunset': data['sys'].get('sunset'),
    }


def fetch_current_weather(city):
    url = f"{BASE_URL}weather?q={city}&appid={API_Key}&units=metric" #construct the api request url
    response = requests.get(url)
    data = response.json()
    if response.status_code != 200:
        message = data.get('message', 'Unable to fetch weather data')
        raise ValueError(message)
    return _serialize_weather(data)


def fetch_weather_by_coordinates(lat, lon):
    lat = float(lat)
    lon = float(lon)
    url = f"{BASE_URL}weather?lat={lat}&lon={lon}&appid={API_Key}&units=metric"
    response = requests.get(url)
    data = response.json()
    if response.status_code != 200:
        message = data.get('message', 'Unable to fetch weather data')
        raise ValueError(message)
    return _serialize_weather(data)


def fetch_hourly_forecast(lat, lon, count=5):
    lat = float(lat)
    lon = float(lon)
    url = f"{BASE_URL}forecast?lat={lat}&lon={lon}&appid={API_Key}&units=metric&cnt={count}"
    response = requests.get(url)
    data = response.json()
    if response.status_code != 200:
        message = data.get('message', 'Unable to fetch forecast data')
        raise ValueError(message)

    tz_offset_seconds = data.get('city', {}).get('timezone', 0)
    tzinfo = pytz.FixedOffset(int(tz_offset_seconds / 60)) if tz_offset_seconds is not None else pytz.utc

    entries = []
    for entry in data.get('list', [])[:count]:
        dt = datetime.fromtimestamp(entry['dt'], tzinfo)
        entries.append({
            'time': dt.strftime("%H:%M"),
            'temp': f"{round(entry['main']['temp'], 1)}",
            'humidity': f"{round(entry['main']['humidity'], 1)}",
            'description': entry['weather'][0]['description'],
        })

    return entries, tzinfo

#Read historical data 

def read_historical_data(filename):
    df = pd.read_csv(filename) #this read csv file into dataframe
    df = df.dropna() #remove rows with missing values
    df = df.drop_duplicates() #remove duplicate rows
    return df


#Prepare data for training

def prepare_data(data):
    le = LabelEncoder() #create a labelEncounter instance 
    data['WindGustDir'] = le.fit_transform(data['WindGustDir'])
    data['RainTomorrow'] = le.fit_transform(data['RainTomorrow'])

    #define feature variable and target variables
    X = data[['MinTemp', 'MaxTemp', 'WindGustDir', 'WindGustSpeed', 'Humidity', 'Pressure', 'Temp']] #feature variables
    y = data['RainTomorrow'] #target variable

    return X, y, le  #return feature variable, target variable and label encoder


#Train Rain predication model

def train_rain_model(X, y):
  X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
  model = RandomForestClassifier(n_estimators=100, random_state=42)
  model.fit(X_train, y_train) #train the model

  y_pred = model.predict(X_test) #to make prediction on test set
  accuracy = np.mean(y_pred == y_test)

  print("Mean square error for Rain model")
  print(mean_squared_error(y_test, y_pred))

  print(f'Accuracy: {accuracy}')
  return model

def _description_class(description: str) -> str:
    if not description:
        return 'no-forecast'
    primary = description.split()[0].lower()
    synonyms = {
        'broken': 'clouds',
        'scattered': 'clouds',
        'few': 'clouds',
        'partly': 'clouds',
        'light': 'light',
        'moderate': 'moderate',
        'heavy': 'rain',
    }
    return synonyms.get(primary, primary)


def _format_timestamp(timestamp, tzinfo):
    if not timestamp:
        return '--'
    dt = datetime.fromtimestamp(timestamp, tzinfo)
    return dt.strftime("%I:%M %p")


def build_weather_context(city, *, current_weather=None):
    if not city:
        raise ValueError('City name is required')

    if current_weather is None:
        current_weather = fetch_current_weather(city)

    lat = current_weather.get('lat')
    lon = current_weather.get('lon')
    forecast_entries = []
    location_tz = pytz.utc
    if lat is not None and lon is not None:
        try:
            forecast_entries, location_tz = fetch_hourly_forecast(lat, lon)
        except Exception:
            logging.exception('Unable to fetch hourly forecast for %s', city)

    # Use a path relative to this file to find the project's weather.csv
    rain_outlook = 'Rain outlook unavailable'
    try:
        csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'weather.csv'))
        data = read_historical_data(csv_path)
        X, y, le = prepare_data(data)
        rain_model = train_rain_model(X, y)

        wind_deg = current_weather['wind_gust_dir'] % 360
        compass_points = [
            ("N", 0, 11.25), ("NNE", 11.25, 33.75), ("NE", 33.75, 56.25),
            ("ENE", 56.25, 78.75), ("E", 78.75, 101.25), ("ESE", 101.25, 123.75),
            ("SE", 123.75, 146.25), ("SSE", 146.25, 168.75), ("S", 168.75, 191.25),
            ("SSW", 191.25, 213.75), ("SW", 213.75, 236.25), ("WSW", 236.25, 258.75),
            ("W", 258.75, 281.25), ("WNW", 281.25, 303.75), ("NW", 303.75, 326.25),
            ("NNW", 326.25, 348.75)
        ]
        compass_direction = next((point for point, start, end in compass_points if start < wind_deg < end), "Unknown")
        if compass_direction != "Unknown" and compass_direction in le.classes_:
            compass_direction_encoded = le.transform([compass_direction])[0]
        else:
            compass_direction_encoded = -1

        current_data = {
            'MinTemp': current_weather['temp_min'],
            'MaxTemp': current_weather['temp_max'],
            'WindGustDir': compass_direction_encoded,
            'WindGustSpeed': current_weather['wind_gust_speed'],
            'Humidity': current_weather['humidity'],
            'Pressure': current_weather['pressure'],
            'Temp': current_weather['current_temp'],
        }
        current_df = pd.DataFrame([current_data])
        rain_prediction = rain_model.predict(current_df)[0]
        rain_outlook = 'Rain likely soon' if rain_prediction == 1 else 'Low chance of rain'
    except Exception:
        logging.exception('Rain model failed to compute outlook')

    now = datetime.now(location_tz)

    sunrise_str = _format_timestamp(current_weather.get('sunrise'), location_tz)
    sunset_str = _format_timestamp(current_weather.get('sunset'), location_tz)

    context = {
        'location': city,
        'current_temp': str(current_weather['current_temp']),
        'MinTemp': str(current_weather['temp_min']),
        'MaxTemp': str(current_weather['temp_max']),
        'feels_like': str(current_weather['feels_like']),
        'humidity': str(current_weather['humidity']),
        'clouds': str(current_weather['clouds']),
        'description': current_weather['description'],
        'description_class': _description_class(current_weather['description']),
        'city': current_weather['city'],
        'country': current_weather['country'],
        'time': now.strftime("%I:%M %p"),
        'date': now.strftime("%B %d, %Y"),
        'wind': str(current_weather['wind_gust_speed']),
        'pressure': str(current_weather['pressure']),
        'visibility': str(current_weather['Visibility']),
        'sunrise': sunrise_str,
        'sunset': sunset_str,
        'rain_outlook': rain_outlook,
        'forecast': forecast_entries,
        'updated_at': datetime.utcnow().isoformat() + 'Z',
    }
    return context


#Weather analysis function
def weather_view(request):
    base_context = {
        'description': 'No forecast yet',
        'description_class': 'no-forecast',
        'location': '',
        'current_temp': '--',
        'feels_like': '--',
        'humidity': '--',
        'clouds': '--',
        'city': '',
        'country': '',
        'time': '',
        'date': '',
        'wind': '--',
        'pressure': '--',
        'visibility': '--',
        'MinTemp': '--',
        'MaxTemp': '--',
        'sunrise': '--',
        'sunset': '--',
        'rain_outlook': 'Rain outlook unavailable',
        'forecast': [],
        'updated_at': '',
        'fallback_city': DEFAULT_CITY,
        'error_message': '',
    }

    if request.method == 'POST':
        city = request.POST.get('city')
        if not city:
            return render(request, 'weather.html', {
                **base_context,
                'error_message': 'Please enter a city name.',
            })
        try:
            context = build_weather_context(city)
        except ValueError as exc:
            return render(request, 'weather.html', {
                **base_context,
                'error_message': str(exc),
            })
        except Exception as exc:
            logging.exception('Error processing weather request')
            return render(request, 'weather.html', {
                **base_context,
                'error_message': f"An error occurred while processing your request: {exc}",
            })
        context['fallback_city'] = DEFAULT_CITY
        return render(request, 'weather.html', context)

    return render(request, 'weather.html', base_context)


def healthz(request):
    # Simple health endpoint for load balancers and platform probes
    return JsonResponse({'status': 'ok'})


@require_POST
def auto_location(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request payload'}, status=400)

    lat = payload.get('lat')
    lon = payload.get('lon')
    fallback_city = payload.get('fallback_city')
    city_param = payload.get('city')

    try:
        if city_param:
            current_weather = fetch_current_weather(city_param)
            city = current_weather['city']
        elif lat is not None and lon is not None:
            current_weather = fetch_weather_by_coordinates(lat, lon)
            city = current_weather['city']
        elif fallback_city:
            current_weather = None
            city = fallback_city
        else:
            return JsonResponse({'error': 'Missing coordinates'}, status=400)

        context = build_weather_context(city, current_weather=current_weather)
        context['fallback_city'] = DEFAULT_CITY
        return JsonResponse(context)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except Exception:
        logging.exception('Unable to fetch weather data for auto location request')
        return JsonResponse({'error': 'Unable to determine your location'}, status=502)