from synchrony.views import index
from synchrony.views import logout
from synchrony.views import request


maps = {
		'index':   index.IndexView,
		'logout':  logout.LogoutView,
		'request': request.RequestView,
}
