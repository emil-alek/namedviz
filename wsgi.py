"""WSGI entry point for Gunicorn.

Example:
    gunicorn "wsgi:application"
    gunicorn -w 4 --threads 2 "wsgi:application"
    gunicorn -w 4 --threads 2 -b 0.0.0.0:5000 "wsgi:application"

Set NAMEDVIZ_CONFIG_PATH to pre-load startup configs (equivalent of
passing a path to run.py):
    NAMEDVIZ_CONFIG_PATH=sample_configs/ gunicorn -w 4 --threads 2 "wsgi:application"
"""
import os
from namedviz.app import create_app

application = create_app(os.environ.get("NAMEDVIZ_CONFIG_PATH"))
