from decouple import config


class Config:
    SECRET_KEY = config('SECRET_KEY', default='change-me-in-production')
    DATABASE = config('DATABASE', default='q360.db')
