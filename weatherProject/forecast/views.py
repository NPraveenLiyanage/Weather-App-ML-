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
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor #to build a random forest classification and regression model
from sklearn.metrics import mean_squared_error #to measure the accuracy of our predictions
from datetime import datetime, timedelta #to work with dates and times
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


#Fetch current weather data

def fetch_current_weather(city):
    url = f"{BASE_URL}weather?q={city}&appid={API_Key}&units=metric" #construct the api request url
    response = requests.get(url)
    data = response.json()
    if response.status_code != 200:
        message = data.get('message', 'Unable to fetch weather data')
        raise ValueError(message)
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
        'clouds':data['clouds']['all'],
        'Visibility':data['visibility'],
    }

def fetch_weather_by_coordinates(lat, lon):
    lat = float(lat)
    lon = float(lon)
    url = f"{BASE_URL}weather?lat={lat}&lon={lon}&appid={API_Key}&units=metric"
    response = requests.get(url)
    data = response.json()
    if response.status_code != 200:
        message = data.get('message', 'Unable to fetch weather data')
        raise ValueError(message)
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
        'Visibility': data['visibility'],
    }

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

#Prepare regression data

def prepare_regression_data(data, feature):
  X, y = [], [] #initialze test for feature and target value
  
  for i in range(len(data) - 1):
    X.append(data[feature].iloc[i])
    y.append(data[feature].iloc[i+1])

  X = np.array(X).reshape(-1, 1)
  y = np.array(y)

  return X, y


#Train regression model

def train_regression_model(X, y):
  model = RandomForestRegressor(n_estimators=100, random_state=42)
  model.fit(X, y)
  return model


#Predict Future

def predict_future(model, current_value):
  predictions = [current_value]

  for i in range(5):
    next_value = model.predict(np.array([[predictions[-1]]]))
    predictions.append(next_value[0])

  return predictions[1:]


#Weather analysis function
def weather_view(request):
    if request.method == 'POST':
        city = request.POST.get('city')
        error_message = None
        current_weather = None
        try:
            current_weather = fetch_current_weather(city)
        except Exception as e:
            error_message = "Invalid city name or unable to fetch weather data. Please enter a valid city."
        if not current_weather or 'city' not in current_weather:
            error_message = "Invalid city name or unable to fetch weather data. Please enter a valid city."
        if error_message:
            return render(request, 'weather.html', {'error_message': error_message})
        try:
            # Use a path relative to this file to find the project's weather.csv
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
            X_temp, y_temp = prepare_regression_data(data, 'Temp')
            X_hum, y_hum = prepare_regression_data(data, 'Humidity')
            temp_model = train_regression_model(X_temp, y_temp)
            hum_model = train_regression_model(X_hum, y_hum)
            future_temp = predict_future(temp_model, current_weather['temp_min'])
            future_humidity = predict_future(hum_model, current_weather['humidity'])
            timezone = pytz.timezone('Asia/Kolkata')
            now = datetime.now(timezone)
            next_hour = now + timedelta(hours=1)
            next_hour = next_hour.replace(minute=0, second=0, microsecond=0)
            future_times = [(next_hour + timedelta(hours=i)).strftime("%H:00") for i in range(5)]
            time1, time2, time3, time4, time5 = future_times
            temp1, temp2, temp3, temp4, temp5 = future_temp
            hum1, hum2, hum3, hum4, hum5 = future_humidity
            context = {
                'location': city,
                'current_temp': current_weather['current_temp'],
                'MinTemp': current_weather['temp_min'],
                'MaxTemp': current_weather['temp_max'],
                'feels_like': current_weather['feels_like'],
                'humidity': current_weather['humidity'],
                'clouds': current_weather['clouds'],
                'description': current_weather['description'],
                'city': current_weather['city'],
                'country': current_weather['country'],
                'time': datetime.now(),
                'date': datetime.now().strftime("%B %d, %Y"),
                'wind': current_weather['wind_gust_speed'],
                'pressure': current_weather['pressure'],
                'visibility': current_weather['Visibility'],
                'time1': time1,
                'time2': time2,
                'time3': time3,
                'time4': time4,
                'time5': time5,
                'temp1': f"{round(temp1, 1)}",
                'temp2': f"{round(temp2, 1)}",
                'temp3': f"{round(temp3, 1)}",
                'temp4': f"{round(temp4, 1)}",
                'temp5': f"{round(temp5, 1)}",
                'hum1': f"{round(hum1, 1)}",
                'hum2': f"{round(hum2, 1)}",
                'hum3': f"{round(hum3, 1)}",
                'hum4': f"{round(hum4, 1)}",
                'hum5': f"{round(hum5, 1)}",
            }
            return render(request, 'weather.html', context)
        except Exception as e:
            logging.exception('Error processing weather request')
            error_message = f"An error occurred while processing your request: {e}"
            return render(request, 'weather.html', {'error_message': error_message})
    # Provide default values for forecast variables to avoid JS errors on initial GET
    # Provide defaults so the template renders useful placeholders on initial GET
    return render(request, 'weather.html', {
        'description': 'No forecast yet',
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
        'time1': '', 'time2': '', 'time3': '', 'time4': '', 'time5': '',
        'temp1': '', 'temp2': '', 'temp3': '', 'temp4': '', 'temp5': '',
        'hum1': '', 'hum2': '', 'hum3': '', 'hum4': '', 'hum5': ''
    })


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
    if lat is None or lon is None:
        return JsonResponse({'error': 'Missing coordinates'}, status=400)

    try:
        current_weather = fetch_weather_by_coordinates(lat, lon)
    except Exception:
        logging.exception('Unable to fetch weather for coordinates %s, %s', lat, lon)
        return JsonResponse({'error': 'Unable to determine your location'}, status=502)

    return JsonResponse({
        'city': current_weather['city'],
        'country': current_weather['country'],
    })