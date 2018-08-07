# ENABLE ENVIRONMENT VARIABLES FROM FLASK CONFIG
import os

# LOG LEVEL
DEBUG = 1

# LOG
LOG_FORMAT = "%(asctime)s [%(levelname)s] IRSAPI[%(process)d/%(threadName)s].%(name)s: %(message)s"
LOG_FILE = "/dev/stdout"

#ILO and HP IRS CONFIG
ILO_USERNAME="Administrator"
ILO_PASSWORD="****"
ERS_DESTINATION_PORT="7906"

# HP IRS DATABASE CONFIG
DB_USERNAME="ro_user"
DB_PASSWORD="*****"
IRS_DATABASE="UCA"
DB_PORT="7950"
