"""
This endpoint is mainly for populating the UI with an overview of how many
sites have been cached.
"""
from sqlalchemy import and_
from flask.ext import restful
from flask import session, request
from synchrony.models import Domain
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import Pagination, make_response

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

class DomainResource(restful.Resource):

    def get(self, domain):
        """

        """
        auth(session, required=True)
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",type=int, help="", required=False, default=1)
        parser.add_argument("per_page",type=int, help="", required=False, default=10)
        args = parser.parse_args()

        domain = Domain.query.filter(Domain.name == domain).first()
        if not domain:
            return {}, 404

        pages = Pagination(domain.resources, args.page, args.per_page)
        return make_response(request.url, pages)

class DomainCountResource(restful.Resource):
    """
    Returns an integer.
    """
    def get(self):
        return Domain.query.count()
