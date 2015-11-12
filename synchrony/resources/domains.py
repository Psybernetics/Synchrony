"""
This endpoint is mainly for populating the UI with an overview of how many
sites have been cached.
"""
from flask.ext import restful
from synchrony.models import Domain
from flask import session, request
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import make_response

class DomainCollection(restful.Resource):

    def get(self):
        """
        A paginated resource for Domains
        """
        auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",type=int, required=False, default=1)
        parser.add_argument("per_page",type=int, required=False, default=10)
        args = parser.parse_args()

        query = Domain.query.paginate(args.page, args.per_page)

        return make_response(request.url, query)

class DomainCountResource(restful.Resource):
    """
    Return the total number of domains we're storing. Doesn't require auth.
    """
    def get(self):
        return Domain.query.count()
