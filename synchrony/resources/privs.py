import flask_restful as restful
from sqlalchemy import and_, desc
from flask import request, session
from synchrony import app, db, log
from synchrony.models import Priv
from synchrony.controllers.auth import auth
from synchrony.controllers.utils import make_response

class PrivCollection(restful.Resource):
    def get(self):
        """
        Implements /v1/privs
        """
        parser = restful.reqparse.RequestParser()
        parser.add_argument("page",     type=int, required=False, default=1)
        parser.add_argument("per_page", type=int, required=False, default=10)
        args = parser.parse_args()

        user = auth(session, required=True)

        if not user.can("see_all"):
            return {}, 403

        query = Priv.query.order_by(desc(Priv.created)).paginate(args.page, args.per_page)
        return make_response(request.url, query)
