import os

if 'UROKO_DATABASE' in os.environ:
	SQLALCHEMY_DATABASE_URI = os.environ['UROKO_DATABASE']
else:
	SQLALCHEMY_DATABASE_URI = "sqlite:///cache.db"

# Let users without accounts reap the benefits of decentralised web pages:
OPEN_PROXY = True

# If you haven't got an internet connection change this to 0.01
# to reduce the time taken before the system decides to check
# peers and the database:
HTTP_TIMEOUT = 1.00

# Allow people to register accounts on the login screen
PERMIT_NEW_ACCOUNTS = True
