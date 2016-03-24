# This file defines the /v1/config endpoint for adjusting app.config
# during runtime
from flask import session
import flask_restful as restful
from flask_restful import reqparse

from synchrony import app, log
from synchrony.controllers.auth import auth

def config_as_response():
    response = dict(app.config)
    del response["SECRET_KEY"]
    del response["SQLALCHEMY_DATABASE_URI"]
    for key in response.copy():
        if not isinstance(response[key],
        (float, int, unicode, str, dict, list)):
            del response[key]
    return response

class ConfigCollection(restful.Resource):
    """
    Implements /v1/config
    """
    def get(self):
        user = auth(session, required=True)
        
        if not user.can("see_all"):
            return {}, 403

        return config_as_response()

    def post(self):
        user = auth(session, required=True)
        if not user.can("toggle_signups"):
            return {}, 403

        # Explicit parser options for 1) specifying types,
        # 2) limiting surface area.
        parser = reqparse.RequestParser()
        parser.add_argument("OPEN_PROXY",          type=bool,  default=None)
        parser.add_argument("HTTP_TIMEOUT",        type=float, default=None)
        parser.add_argument("PERMIT_NEW_ACCOUNTS", type=bool,  default=None)
        parser.add_argument("NO_PRISONERS",        type=bool,  default=None)
        parser.add_argument("DISABLE_JAVASCRIPT",  type=bool,  default=None)
        args = parser.parse_args()


        # Eg: Use {"OPEN_PROXY": null} to disable these via JavaScript.
        if args.OPEN_PROXY != None:
            app.config["OPEN_PROXY"] = args.OPEN_PROXY

        if args.HTTP_TIMEOUT != None:
            app.config["HTTP_TIMEOUT"] = args.HTTP_TIMEOUT

        if args.PERMIT_NEW_ACCOUNTS != None:
            app.config["PERMIT_NEW_ACCOUNTS"] = args.PERMIT_NEW_ACCOUNTS

        if args.NO_PRISONERS != None:
            app.config["NO_PRISONERS"] = args.NO_PRISONERS

        if args.DISABLE_JAVASCRIPT != None:
            app.config["DISABLE_JAVASCRIPT"] = args.DISABLE_JAVASCRIPT

        return config_as_response()
