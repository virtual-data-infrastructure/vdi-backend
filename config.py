# config.py
import os

class Config:
  SQLALCHEMY_DATABASE_URI = 'sqlite:////mnt/vol1/databases/vdi.db'
  SQLALCHEMY_TRACK_MODIFICATIONS = False
  UPLOAD_DIRECTORY = '/mnt/vol1/uploads'
