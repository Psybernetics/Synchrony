"""
Defines a paginated view of overlay networks the application is configured to
accept as legitimate.
"""
from synchrony import app
from flask.ext import restful
from flask import session, request
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import Pagination, make_response

class NetworkCollection(restful.Resource):

    def get(self):
        auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",type=int, help="", required=False, default=1)
        parser.add_argument("per_page",type=int, help="", required=False, default=10)
        args = parser.parse_args()

        pages = Pagination(app.routes.values(), args.page, args.per_page)
        return make_response(request.url, pages)

        # If you're here because you're wondering what the "private" attribute
        # in the responses means: It's for networks composed of nodes who all
        # have the same private/public keypair and will only accept new peers
        # who can decrypt for that key. This is useful for guaranteeing that
        # nodes using --autoreplicate only replicate for your instances.
