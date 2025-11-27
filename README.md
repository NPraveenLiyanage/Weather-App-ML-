# Weather Prediction Web Application 

🌦️ A Django-based web application that provides real-time weather forecasts and machine learning-powered predictions

## Features
- Current weather conditions from OpenWeatherMap API
- Machine learning models for rain prediction (Random Forest Classifier)
- Temperature/Humidity forecasting (Random Forest Regressor)
- 5-hour future weather predictions
- Interactive web interface
- Error handling for invalid inputs

## Technologies
- **Backend**: Python/Django
- **Machine Learning**: Scikit-learn, pandas, numpy
- **Weather Data**: OpenWeatherMap API
- **Frontend**: HTML/CSS (Django Templates)

## Installation
1. Clone repository:
```bash
git clone https://github.com/yourusername/Weather-App-ML.git
```
2. Create virtual environment:
```bash
python -m venv myenv
```
3. Install requirements:
```bash
pip install -r requirements.txt
```
4. Get OpenWeatherMap API key from [their website](https://openweathermap.org/api)
5. Create `.env` file:
```ini
API_KEY=your_openweathermap_api_key
```
6. Run migrations:
```bash
python manage.py migrate
```

## Usage
1. Start development server:
```bash
python manage.py runserver
```
2. Access via `http://localhost:8000`
3. Enter city name to get:
   - Current temperature/humidity
   - Rain prediction
   - 5-hour forecast
   - Wind/pressure/visibility data

## Machine Learning Components
- Rain prediction model trained on historical weather data
- Time series forecasting for temperature/humidity
- Label encoding for categorical data
- Model persistence between sessions

## Project Structure

## Requirements
- Python 3.9+
- Django 4.0+
- pandas
- numpy
- scikit-learn
- python-dotenv
