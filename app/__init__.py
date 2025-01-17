# __init__.py
from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from config import Config

app = Flask(__name__)
# enable CORS (cross-origin resource sharing) for route '/upload' from origin 'vdi.nessi.no'
CORS(app, resources={
    r"/upload/*": {"origins": "https://vdi.nessi.no:5815"},
    r"/projects/*": {"origins": "https://vdi.nessi.no:5815"}
})

print("set up CORS")

app.config.from_object(Config)
db = SQLAlchemy(app)
#migrate = Migrate(app, db)

from app import routes, models
