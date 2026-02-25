# 🌦️ Weather App with ML Rain Prediction

A full-stack weather web application built with **Django** that delivers real-time weather data via the **OpenWeatherMap API** and uses a **Random Forest Classifier (scikit-learn)** trained on historical weather data to predict the probability of rain for the next day.

---

## 📸 Preview

> Search any city → get live conditions, an hourly forecast strip, sunrise/sunset times, wind & pressure stats, and an ML-powered rain outlook — all in one clean interface.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🔍 City search | Lookup any city worldwide |
| 📍 Geolocation | Auto-detect user location via browser GPS |
| 🌡️ Live weather | Temperature, feels-like, humidity, wind, pressure, visibility, clouds |
| ⏱️ Hourly forecast | Next 5-period forecast strip |
| 🌅 Sun times | Sunrise & sunset in the city's local timezone |
| 🤖 ML rain outlook | Random Forest Classifier predicts rain likelihood |
| 🔖 Saved locations | Bookmark favourite cities (persisted in localStorage) |
| 🔔 Personal alerts | Browser notification when rain is likely or temp crosses a threshold |
| 📱 Responsive UI | Mobile-first design with Bootstrap 5 |
| ❤️ Health endpoint | `/healthz` for load-balancer/platform probes |

---

## 🗂️ Project Structure

```
Weather-App(ML)/
├── weather.csv                  # Historical weather dataset (368 records)
├── vercel.json                  # Vercel deployment config
├── Procfile                     # Heroku/Railway process definition
├── Dockerfile                   # Root-level Docker build (Vercel)
├── README.md
├── notebooks/
│   └── model_training.ipynb     # Standalone ML training walkthrough
└── weatherProject/              # Django project root
    ├── manage.py
    ├── requirements.txt
    ├── Dockerfile               # Production Docker image
    ├── docker-compose.yml       # Local multi-container setup
    ├── docker-entrypoint.sh     # Migrate → collectstatic → serve
    ├── weatherProject/          # Django settings package
    │   ├── settings.py
    │   ├── urls.py
    │   ├── wsgi.py
    │   └── asgi.py
    └── forecast/                # Main Django application
        ├── views.py             # All business logic + ML pipeline
        ├── urls.py
        ├── models.py
        ├── templates/
        │   └── weather.html     # Single-page template
        └── static/
            ├── css/styles.css
            └── img/
```

---

## 🧠 Machine Learning Pipeline

The ML pipeline lives entirely in `weatherProject/forecast/views.py` and runs on every weather request.

### Dataset — `weather.csv`

368 records with the following columns:

| Column | Type | Description |
|---|---|---|
| `MinTemp` | float | Minimum temperature (°C) |
| `MaxTemp` | float | Maximum temperature (°C) |
| `WindGustDir` | string | Compass wind gust direction (e.g. NW, ENE) |
| `WindGustSpeed` | float | Wind gust speed (km/h) |
| `Humidity` | float | Relative humidity (%) |
| `Pressure` | float | Atmospheric pressure (hPa) |
| `Temp` | float | Current temperature (°C) |
| `RainTomorrow` | Yes/No | **Target label** |

### Steps

```
1. Load CSV  →  drop NaN & duplicates (pandas)
2. Encode WindGustDir & RainTomorrow  →  LabelEncoder
3. Train / Test split  →  80 / 20  (random_state=42)
4. Fit RandomForestClassifier  →  n_estimators=100
5. Evaluate  →  accuracy + MSE printed to console
6. Predict live  →  map live wind degree → compass label → encode → predict
7. Return  →  "Rain likely soon"  |  "Low chance of rain"
```

### Model Details

| Attribute | Value |
|---|---|
| Algorithm | `RandomForestClassifier` |
| Library | scikit-learn 1.7.0 |
| Estimators | 100 decision trees |
| Test size | 20 % |
| Random state | 42 |
| Feature count | 7 |
| Target classes | `Yes` → 1, `No` → 0 |

> See the full training walkthrough with plots and evaluation metrics in [`notebooks/model_training.ipynb`](notebooks/model_training.ipynb).

---

## 🌐 External API — OpenWeatherMap

This app uses two OpenWeatherMap endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /data/2.5/weather` | Current conditions by city name or lat/lon |
| `GET /data/2.5/forecast` | 3-hour step forecast (next 5 periods) |

All responses use **metric units** (°C, m/s). Get a free API key at [openweathermap.org](https://openweathermap.org/api).

---

## 🛠️ Tech Stack

### Backend
| Technology | Version | Role |
|---|---|---|
| Python | 3.11 | Runtime |
| Django | 5.2.3 | Web framework |
| Gunicorn | 23.0.0 | WSGI production server |
| WhiteNoise | 6.5.0 | Static file serving |
| python-dotenv | 1.1.0 | `.env` file loading |
| dj-database-url | 1.0.0 | `DATABASE_URL` → Django DB config |

### Machine Learning
| Technology | Version | Role |
|---|---|---|
| scikit-learn | 1.7.0 | `RandomForestClassifier`, `LabelEncoder`, `train_test_split` |
| pandas | 2.3.0 | CSV ingestion, DataFrame manipulation |
| NumPy | 2.3.0 | Numerical operations, accuracy calculation |
| SciPy | 1.15.3 | Transitive scikit-learn dependency |

### Frontend
| Technology | Version | Role |
|---|---|---|
| Bootstrap | 5.3.6 | Responsive layout & components |
| Bootstrap Icons | 1.11.3 | Icon set |
| Vanilla JavaScript | — | Geolocation, AJAX, favorites, alerts |
| Custom CSS | — | Glassmorphism weather cards, animated states |

### Database
| Technology | Role |
|---|---|
| SQLite 3 | Default development database |
| PostgreSQL | Production (via `psycopg2-binary 2.9.11`) |

### DevOps & Deployment
| Technology | Role |
|---|---|
| Docker | Containerisation |
| Docker Compose | Local multi-container orchestration |
| Gunicorn | Production WSGI server |
| Vercel | Cloud deployment (`vercel.json`) |
| Heroku / Railway | Alternative via `Procfile` |

---

## ⚙️ Environment Variables

Create a `.env` file in `weatherProject/` (never commit it):

```env
# Required
OPENWEATHER_API_KEY=your_openweathermap_api_key

# Optional – sensible defaults are used in development
DJANGO_SECRET_KEY=your-very-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DEFAULT_CITY=Colombo

# Production database (omit for SQLite)
DATABASE_URL=postgres://user:password@host:5432/dbname
```

> In **production** (`DEBUG=False`), both `DJANGO_SECRET_KEY` and `OPENWEATHER_API_KEY` are **required** — Django will raise `RuntimeError` on startup if they are missing.

---

## 🚀 Quick Start (Local)

### 1 — Clone & create virtual environment

```bash
git clone https://github.com/<your-username>/Weather-App-ML.git
cd Weather-App-ML

python -m venv myenv
# Windows
myenv\Scripts\activate
# macOS / Linux
source myenv/bin/activate
```

### 2 — Install dependencies

```bash
pip install -r weatherProject/requirements.txt
```

### 3 — Configure environment

```bash
# Create weatherProject/.env and set OPENWEATHER_API_KEY
```

### 4 — Run migrations & collect static files

```bash
cd weatherProject
python manage.py migrate
python manage.py collectstatic --noinput
```

### 5 — Start the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

---

## 🐳 Docker

### Build & run with Docker Compose

```bash
cd weatherProject
docker-compose up --build
```

### Build & run manually

```bash
cd weatherProject
docker build -t weather-app .
docker run -p 8000:8000 \
  -e OPENWEATHER_API_KEY=your_key \
  -e DJANGO_SECRET_KEY=your_secret \
  -e DEBUG=False \
  weather-app
```

---

## ☁️ Deployment

### Vercel

```bash
vercel --prod
```

Set the following environment variables in the Vercel dashboard:
- `OPENWEATHER_API_KEY`
- `DJANGO_SECRET_KEY`
- `DEBUG=False`
- `ALLOWED_HOSTS=your-app.vercel.app`

### Heroku / Railway

```bash
heroku create your-app-name
heroku config:set OPENWEATHER_API_KEY=... DJANGO_SECRET_KEY=... DEBUG=False
git push heroku main
```

The `Procfile` defines:
```
web: cd weatherProject && gunicorn weatherProject.wsgi:application
```

---

## 📡 API Endpoints

| Method | URL | Description |
|---|---|---|
| `GET` | `/` | Main weather page |
| `POST` | `/` | Submit city search form |
| `POST` | `/auto-location/` | JSON endpoint for geolocation-based lookup |
| `GET` | `/healthz/` | Health check — returns `{"status": "ok"}` |

### `/auto-location/` Request Body

```json
{
  "lat": 6.9271,
  "lon": 79.8612,
  "fallback_city": "Colombo",
  "city": "optional-city-override"
}
```

---

## 📓 Notebooks

The [`notebooks/`](notebooks/) folder contains a self-contained Jupyter notebook:

- **`model_training.ipynb`** — End-to-end ML walkthrough:
  - Exploratory Data Analysis (EDA)
  - Class distribution & feature correlation heatmap
  - Data preprocessing & encoding
  - Train / test split & model fitting
  - Accuracy, MSE, Confusion Matrix, Classification Report
  - Feature importance bar chart
  - Hyperparameter tuning with `GridSearchCV`
  - Saving & loading the trained model with `joblib`

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -m 'feat: add my feature'`
4. Push to branch: `git push origin feature/my-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the **MIT License**.

---

## 🙏 Acknowledgements

- [OpenWeatherMap](https://openweathermap.org/) for the weather data API
- [scikit-learn](https://scikit-learn.org/) for the ML toolkit
- [Django](https://www.djangoproject.com/) for the web framework
- [Bootstrap](https://getbootstrap.com/) for the UI components
