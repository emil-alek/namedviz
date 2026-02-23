"""WSGI entry point for Gunicorn.

**Important — run with a single worker.**
Session data (uploaded configs) is stored in an in-process dict.
Multiple workers each hold a separate copy, so sessions created in one
worker are invisible to others, causing uploads to silently disappear.

Example:
    gunicorn "wsgi:application"
    gunicorn -w 1 --threads 4 "wsgi:application"
    gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 "wsgi:application"

Set NAMEDVIZ_CONFIG_PATH to pre-load startup configs (equivalent of
passing a path to run.py):
    NAMEDVIZ_CONFIG_PATH=sample_configs/ gunicorn -w 1 --threads 4 "wsgi:application"
"""
import os
from namedviz.app import create_app

application = create_app(os.environ.get("NAMEDVIZ_CONFIG_PATH"))
