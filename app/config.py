from decouple import config


class Config:
    SECRET_KEY = config('SECRET_KEY', default='change-me-in-production')
    DATABASE = config('DATABASE', default='q360.db')
    EMAIL_ADDRESS = config('EMAIL_ADDRESS', default='')
    EMAIL_PASSWORD = config('EMAIL_PASSWORD', default='')
