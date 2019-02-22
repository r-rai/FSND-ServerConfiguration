import os
basedir = os.path.abspath('DB')

class Config(object):
    # ...
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'catalog.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False