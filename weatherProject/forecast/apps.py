from django.apps import AppConfig


class ForecastConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'forecast'

    def ready(self):
        # Keep the 16-place forecast warm in the background (gunicorn / runserver only, not migrate or shell).
        import os, sys
        argv = " ".join(sys.argv).lower()
        if os.environ.get("WX_PREWARM", "1") != "0" and ("gunicorn" in argv or "runserver" in argv):
            from . import predictor
            predictor.prewarm()
