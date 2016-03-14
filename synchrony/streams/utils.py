from synchrony import log
from synchrony.controllers.auth import auth
from socketio.namespace import BaseNamespace

class Stream(BaseNamespace):

    socket_type = ""

    def broadcast(self, channel, event, *args):
        pkt = dict(type="event",
                   name=event,
                   args=args,
                   endpoint=self.ns_name)
        channel_name = self.get_channel_name(channel)
        for sessid, socket in self.socket.server.sockets.iteritems():
            if 'channels' not in socket.session:
                continue
            if channel_name in socket.session['channels'] \
            and self.socket != socket:
                socket.send_packet(pkt)

    def recv_connect(self):
        self.authenticate()

    def join(self, channel, channel_type="name"):
        self.session['channels'].add(self.get_channel_name(channel))
        if hasattr(self, "channel"):
            self.channel = (channel_type, channel)
        
    def leave(self, channel):
        self.session['channels'].remove(self.get_channel_name(channel))

    def get_channel_name(self, channel):
        return self.ns_name + '_' + channel

    def authenticate(self):
        if not self.user:
            user = auth(self.request)
            if user and not self.user:
                log("Received %s stream connection from %s" % \
                    (self.socket_type, user.username))
                self.user = user
                return True
            return False

    @property
    def itersockets(self):
        """
        Return other active connections in this same namespace. 
        """
        connections = []
        for c in self.socket.server.sockets.values():
            if c.connected:
                for ns in c.active_ns.values():
                    if ns != self and ns.ns_name == self.ns_name:
                        connections.append(ns)
        return connections

def require_auth(func):
    def wrapper(self, *args, **kwargs):
        if not self.user:
            user = auth(self.request)
            if not user: return
            self.user = user
        return func(self, *args)

    wrapper.__doc__ = func.__doc__
    return wrapper

def get_sessions():
    pass

def broadcast(httpd, socket_type, message_type, message, user=None, priv=None):
    """
    Send JSON data to stream users either specifically or by access control.
    """
    sent = 0
    for connection in httpd.sockets.values():
        if connection.connected and connection.socket_type == socket_type:
            for c in connection.active_ns.values():
                if not hasattr(c, "socket_type") or c.socket_type != socket_type:
                    continue
                if not hasattr(c, "user"):
                    continue
                if priv and not c.user.can(priv):
                    continue
                if user and c.user.uid != user.uid:
                    continue
                c.emit(message_type, message)
                sent += 1
    return sent

def check_availability(httpd, socket_type, user):
    """
    Return True if the specified user has an active connection to the specified
    socket type, False otherwise.
    """
    
    for connection in httpd.sockets.values():
        if connection.connected and connection.socket_type == socket_type:
            for c in connection.active_ns.values():
                if not hasattr(c, "socket_type") or c.socket_type != socket_type:
                    continue
                if not hasattr(c, "user"):
                    continue
                if c.user.uid != user.uid:
                    continue
                return True
    return False

def change_channel(httpd, socket_type, user, channel):
    """
    Force a stream user to join an in-stream channel.
    Useful for enabling people to reply to RPC_CHAT messages.
    """
    
    for connection in httpd.sockets.values():
        if connection.connected and connection.socket_type == socket_type:
            for c in connection.active_ns.values():
                if not hasattr(c, "socket_type") or c.socket_type != socket_type:
                    continue
                if not hasattr(c, "user"):
                    continue
                if user and c.user.uid != user.uid:
                    continue
                print "Joining %s to %s." % (user.username, channel) 
                c.on_join(channel)

