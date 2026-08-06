import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DJANGO_SECRET_KEY", "x" * 50)
os.environ.setdefault("USE_SQLITE", "1")

from config.settings.test import *

STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}
