---------activacion del entorno virtual ---------------
virtualenv .venv
source app/.venv/Scripts/activate
----------corre el programa-----------------------------
export FLASK_APP=app
export FLASK_ENV=development
flask run
---------------------------------------
