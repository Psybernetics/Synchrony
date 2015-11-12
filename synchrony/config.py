import os

if 'UROKO_DATABASE' in os.environ:
	SQLALCHEMY_DATABASE_URI = os.environ['UROKO_DATABASE']
else:
	SQLALCHEMY_DATABASE_URI = "sqlite:///cache.db"

# Let users without accounts reap the benefits of decentralised web pages:
OPEN_PROXY = True

HTTP_TIMEOUT = 1.00
