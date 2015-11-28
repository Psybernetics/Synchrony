from synchrony import log, db
from synchrony.models import UserGroup, Priv, Acl

def init_user_groups():
    """
       Administrators:
            see_all
            delete_at_will
            reset_user_pw
            modify_usergroup
            deactivate
            manage_networks
            review_downloads
        Users:
            chat
            initiate_rtc
            create_revision
            retrieve_from_dht
            browse_peer_nodes
            retrieve_resource
            stream_document

    There's also a secret privilege called "eval" that we don't create but is
    checked for in streams.chat.on_cmd. Perhaps make a special UserGroup for
    yourself.
    """
    # Bans happen by setting User.active to False and clearing their existing sessions.
    groups = ["Administrators", "Users"]
    privs  = [ "see_all", "delete_at_will", "reset_user_pw", "modify_usergroup",
               "deactivate", "manage_networks", "review_downloads", 
               "create_revision_group", "delete_revision_group", "chat",
               "initiate_rtc", "create_revision", "retrieve_from_dht", 
               "browse_peer_nodes", "retrieve_resource", "stream_document"]

    if not Priv.query.first():
        log("Creating privileges.")

    for priv in privs:
        p = Priv.query.filter(Priv.name == priv).first()
        if not p:
            p = Priv(name=priv)
            db.session.add(p)
            db.session.commit()

    for group in groups:
        g = UserGroup.query.filter(UserGroup.name == group).first()
        if not g:
            g = UserGroup(name=group)
            for p in Priv.query.all():
                if group != "Administrators" and p.name in \
                        ["see_all", "delete_at_will", "reset_user_pw", "modify_usergroup",
                         "deactivate", "manage_networks", "review_downloads"]:
                    continue
                a         = Acl()
                a.group   = g
                a.priv    = p
                a.allowed = True
                db.session.add(a)
                db.session.add(p)
                db.session.commit()
            db.session.add(g)
            db.session.commit()
            log("Created user group \"%s\"." % group)

def ban(user):
    pass

def unban(user):
    pass
