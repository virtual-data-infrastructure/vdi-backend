# __init__.py
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from config import Config

app = Flask(__name__)
# enable CORS (cross-origin resource sharing) for routes from origin 'vdi.nessi.no'
CORS(app, resources={
    r"/dataflow/*": {"origins": "https://vdi.nessi.no:5815"},
    r"/projects/*": {"origins": "https://vdi.nessi.no:5815"},
    r"/upload/*": {"origins": "https://vdi.nessi.no:5815"},
    r"/views/*": {"origins": "https://vdi.nessi.no:5815"},
    r"/data/*": {"origins": "https://vdi.nessi.no:5815"},
    r"/download/*": {"origins": "*"},
})

app.config.from_object(Config)
db = SQLAlchemy(app)

from app import routes, models
