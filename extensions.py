"""
extensions.py — Instanciation des extensions Flask
Importé par app.py ET models.py pour éviter les imports circulaires.
"""
#sql alchemy est une bibliotheque python permettant de faire des requetes en utilisant des classes python
#plutot que des requetes sql brutes
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
