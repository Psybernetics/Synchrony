/* 
   Synchrony 0.0.1
   A soft-realtime collaborative hyperdocument editor.
   Copyright Luke Brooks 2015

TODO:

DELETE  /v1/users/:name/sessions

/v1/request/:url   Resource status metadata
/request/:url      Raw resource
/#request/:url     JavaScript to load /request/:url into .content

The iframe in .content will navigate around a site
the /request/:url endpoint merely needs to remove javascript so as not to interfere with the window object.
We can then monitor events in the iframe.


 Global stream [Notify of remote sign-ins]
 localStorage controls
 Administrative chat controls.
 Ownership data.
 Allow owners to toggle public flag on revisions
 document group revision limit
 whichever threshold is met first
 formatted JSON event messages,
 {d:title, +chr@46,r:hash,s:[usernames]}
 OT, hash content, compare, major sync if necessary.
 An awareness of revision histories in streaming
 An awareness of page deletions in streaming
 Reduce the amount of objects used
 Account View (sessions, bio, undelete)
 Account Pages View (search, histories)
 Renaming based on checking availability
 Installation docs
 A favicon.ico
 Compress the javascript includes to a single file.

 Use /#settings to toggle:
  * Preferred peers.
  * Whether to transmit browsing activity.
    The default setting for User objects is to be private.
    This means not transmitting newly saved objects.

*/

// App init
(function(){
    window.App = {
        Config:        {},
        Views:         {},
        stream:        [],
        history:       [],
        title: " - Synchrony",
    }

    // Ask the server who we are.
    $.get("/v1/users?me=1", function(data, status){
        App.Config.user = data;
    });

//    var m = new moment();
//    if (m.hour() >= 20 || m.hour() <= 6){
        setTimeout(function(){
            $('.main').addClass("after-hours");
        }, 50);
//    }

})();

// Tell Ractive.load where our mustache templates live.
Ractive.load.baseUrl = '/static/templates/';

// Tell Backbone where our API endpoints are for documents.
App.Document  = Backbone.Model.extend({urlRoot: '/v1/pages' });
App.Documents = Backbone.Collection.extend({
    model: App.Document,
    url: '/v1/pages',
    paginate: function(perPage, page) {
        page = page - 1;
        var collection = this;
        collection = _(collection.rest(perPage*page));
        collection = _(collection.first(perPage));    
        return collection.map( function(model) { return model.toJSON() }); 
    },
});

//  URL hashes -> attributes on this router
App.Router = Backbone.Router.extend({
    routes: {
        '':                    'index',
//        'request':             'requestindex',
//        'request/:resource':   'requestpage',
        'user/:username':      'userview',
        'peers':               'peersview',
        'settings':            'settingsview',
        'sessions':            'sessionsview',
        'account/objects':     'accountobjects',
        'account/pages/groups':'accountpagegroups',
        'manage':              'manageview',
        'manage/pages':        'managepages',
        'manage/pages/groups': 'managepagegroups',
        'manage/users':        'manageusers',
        'chat':                'chatview',
        'login':               'loginview',
        'logout':              'logout',
        ':page':                'index',
//        '*default': 'renderError',
    },

//    Attributes -> functions in the environment
    index:              indexView,
//    requestindex:       requestIndex,
//    requestresource:    requestView,
    userview:           userView,
    peersview:          peersView,
    settingsview:       settingsView,
    sessionsview:       sessionsView,
    accountobjects:     accountObjects,
    accountpagegroups:  accountPageGroups,
    manageview:         manageView,
    managepages:        managePages,
    managepagegroups:   managePageGroups,
    manageusers:        manageUsers,
    chatview:           chatView,
    loginview:          loginView,
    logout:             logout,

//    Any pre-post render behaviors
    before: function() {
        if (location.hash == '') {
            $('.main').addClass("main_background");
        }
    },
    after: function() {
        if (location.hash != '') {
            $('.main').removeClass("main_background");
        }
    },
});

// Our error handler prints to the stream for ten seconds
function renderError(statement) {
    console.log('Error: ' + statement);
    App.stream.push(statement);
    setTimeout(function(){ App.stream.pop(); }, 10000);
}

// Push a global message to the stream for eight seconds
function renderGlobal(statement) {
    console.log('Global: ' + statement);
    App.stream.reverse();
    App.stream.push( '<span class="global-message">' + statement + '</span>' );
    App.stream.reverse();
    setTimeout(function(){
        App.stream.pop();
        App.stream.reverse();
    }, 60000);
}

// Push $user is typing to the stream for three seconds
function renderTyping(statement) {
    App.stream.push( '<span class="global-message">' + statement + '</span>' );
    setTimeout(function(){ App.stream.pop(); }, 1000);
}

function linkUser(username){
    return '<a href="/#user/' + username + '">' + username + '</a>';
}

// Return a collection of documents with their modification times in english
function upDate(docs){
    var docs_copy = docs.slice(0);
    for (var i = 0; i < docs.length; i++){
        var ts = docs[i].modified;
        docs_copy[i].modified = timeStamp(ts);
    }
    return docs_copy;
}

function pulseChat(){
    $("body").addClass("urgent-sidebar");
    setTimeout(function(){ $("body").removeClass("urgent-sidebar") }, 1000);
}

function paginate(list, page, per_page){
    if (per_page === "undefined"){ per_page = 10; }
    return list.slice(page * per_page - per_page, page * per_page)
}

function notify(message){
    if (!"Notification" in window) { return; }
    if (Notification.permission != "granted") {
        Notification.requestPermission();
    }
    var options = {icon:'/static/img/synchrony.png'};
    var notification = new Notification(message, options);
}

function toggle_synchrony(){
    if (App.Config.user){
        if (!$('.synchrony').hasClass("expanded")){
            update_synchrony();
            $('.synchrony').addClass("expanded");
            $('.synchrony').removeClass("contracted");
        } else {
            $('.synchrony').removeClass("expanded");
            $('.synchrony').addClass("contracted");
        }

        if (!$('.synchrony').hasClass("circular")){
            $('.synchrony').addClass("circular");
            $('.control_panel').hide();
        } else {
            $('.synchrony').removeClass("circular");
            $('.control_panel').show();
        }
    }
}

// This is for populating synchrony.tmpl on mouseover.
function update_synchrony(){
    $.get('/v1/networks', function(r){
        App.Views.synchrony.set({peers: r.data[0].peers});
    });
    $.get('/v1/domains/count', function(r){
        App.Views.synchrony.set({domains: r});
    });
}

function toggleMain(){
    if ($('.main').is(':visible')) {
        $('.main').hide();
        $('.show-hide').html('Show');
    } else {
        $('.main').show();
        $('.show-hide').html('Hide');
    }
}

function request(event){
    if (event.original.keyCode == 13){
        event.original.preventDefault();

        // Grab the iframe div
        var iframe = $('.iframe');

        // Remove any schema from the url
        var url = this.get("url");
        if (url.indexOf("://") > -1){
                url = url.slice(url.indexOf("://")+3, url.length);
        }
        if ($('.main').is(':visible')) {
            toggleMain();
        }

        function update_address_bars(url) {
            location.hash = "request/" + url;
            if (App.Views.index != undefined) {
                App.Views.index.set({url: url});
            }
            if (App.Views.synchrony != undefined) {
                App.Views.synchrony.set({url: url});
            }
        }
        
        update_address_bars(url);
        App.history.push(url);

        $('iframe').contents().find('body').html("Loading...");

        $.ajax({
            type: "GET",
            url: "/request/" + url,
            success: function(data, status){
                iframe.contents().find('body').html(data);

                // Bind a callback to anchor tags so their href attribute
                // is appended to App.history when clicked.
                iframe.contents().find('a').on('click', function(){
                    var url = $(this).attr('href').split('/');
                    url     = url.slice(2, url.length).join('/');
                    App.history.push(url);
                    update_address_bars(url);
               });
                // Also caching the unedited document in the event it's ever
                // sent directly over webrtc.
                App.document = data;
//                $('.external_resources').html(data);
            },
            error: function(data, status){
                renderError(data.responseJSON.message);
            }
        });
    }
}

// Start the Backbone URL hash monitor
new App.Router();
Backbone.history.start();

function indexView(page){
    document.title = "Welcome" + App.title;
    Ractive.load({
        index: 'index.tmpl',
    }).then(function(components){
        if (!App.Config.user) {
            location.hash = "login";
        }

        App.Views['index'] = new components.index({
            el: $('.main'),
            data: App.Config,
            adaptor: ['Backbone'],
        });

        if (!$('.main').is(':visible')) {
            toggleMain();
        }

        if (!$('.main').hasClass('main_background')){
            $('.main').addClass("main_background");
        }

        // Get the initial set of visible revisions
        function populate_revision_table(url){
            $.get(url, function(data){
                App.Views.index.set("paging_error", undefined);
                App.Views.index.set("revisions", data.data);
                App.Views.index.revisions = data;

                // back_available in index.tmpl
                if (data.links.hasOwnProperty("self")) {
                    var url = data.links.self.split('page=')[1];
                    if (url != undefined) {
                        // Change the url hash to reflect subpage
                        window.location.hash = "/" + url;
                        if (url > 1) {
                            App.Views.index.set("back_available", true);
                        } else {
                            App.Views.index.set("back_available", false);
                        }
                    } 
                }

                // forward_available in index.tmpl
                if (data.links.hasOwnProperty("next")) {
                    App.Views.index.set("forward_available", true);
                }
            }).fail(function(){
               App.Views.index.set("paging_error", true);
            });
        }

        // Support direct linking to subviews
        if (page != undefined) {
            populate_revision_table('/v1/revisions?page=' + page);
        } else {
            populate_revision_table('/v1/revisions');
        }

        App.Views.index.on({

            forward: function(event){
                var url = this.revisions.links.next;
                populate_revision_table(url);
            },
            back:    function(event){
                var url = this.revisions.links.self.split('page=');
                var page = url[1] - 1;
                populate_revision_table(url[0] + 'page=' + page);
            },
            // index template addressbar
            request: request, // globally available request function
       });
    });
}

function logout(){
//    location = '/logout/';    
    $.ajax({
        type: "DELETE",
        url: "/v1/users/" + username + "/sessions",
        data: {timestamp: App.config.user.session.created},
        success: function(data, status){
            console.log(data);
            console.log("Logged out");
            App.Config.user = null;
            App.Views.synchrony.set("Config", App.Config);
            location.hash = '';
            location = '/';
        },
        error: function(data, status){
            console.log("Error logging out:" + data);
        }
    });
}


function accountObjects(params){

    document.title = "Your pages" + App.title;
    Ractive.load({
        accountpages: 'accountpages.tmpl',
    }).then(function(components){

        App.Views['accountpages'] = new components.accountpages({
            el: $('.original'),
            data: { user: App.Config.user },
            adaptor: ['Backbone'],
        });

        $.get('/v1/users/' + App.Config.user.username + '/pages',
            function(data, status){
                for (var i = 0; i < data.pages.length; i++){
                    var ts = data.pages[i].created;
                    data.pages[i].timestamp = ts
                    data.pages[i].created = timeStamp(ts);
                    data.pages[i].index = i;
                }
                for (var i = 0; i < data.edits.length; i++){
                    var ts = data.edits[i].created;
                    data.edits[i].timestamp = ts
                    data.edits[i].created = timeStamp(ts);
                    data.edits[i].index = i;
                }
                App.Views.accountpages.set({user: data});
        }).fail(function(){
            renderError("Couldn't contact the document server.");
        });
        $.get('/v1/users/' + App.Config.user.username + '/pages?deleted=1',
            function(data, status){
                for (var i = 0; i < data.length; i++){
                    var ts = data[i].created;
                    data[i].timestamp = ts
                    data[i].created = timeStamp(ts);
                    data[i].index = i;
                }
                App.Views.accountpages.set({deleted_pages: data});
        }).fail(function(){
            renderError("Couldn't retrieve deleted pages");
        });

        App.Views.accountpages.on({
            toggle_edits: function(){
                $('.hidden-table').toggle();
                if (!App.Views.accountpages.showing_edits){
                    App.Views.accountpages.showing_edits = true;
                    $('.edits-button').html("Hide");
                } else {
                    App.Views.accountpages.showing_edits = false;
                    $('.edits-button').html("Show");
                }
            },
        });

    });
}

function peersView(){
    document.title = "Peer Browser" + App.title;
    Ractive.load({
        peers: 'peers.tmpl',
    }).then(function(components){
        if (!App.Config.user) {
            location.hash = "login";
        }

        App.Views['peers'] = new components.peers({
            el: $('.main'),
            data: App.Config,
            adaptor: ['Backbone'],
        });

        // Populate the page.
        // Should be /v1/networks/<name>/peers
        $.get('/v1/peers', function(response){
            console.log(response.data);
            App.Views.peers.set("peers", response.data);
        });

        $.get('/v1/revisions/downloads', function(response){
            console.log(response.data);
            App.Views.peers.set("downloads", response.data);
        });

        // POST /v1/revisions/downloads/<network>/<hash>
        // {reason: integer_severity_level}
        App.Views.peers.on({
            select: function(event, type, index){
                console.log(event);
                if (type === "url") {
                    var index = event.node.parentElement.parentElement.id;
                    var network = this.get("downloads." + index);
                    console.log(network);
                    for (i in network.downloads) {
                        var downloads = network.downloads[i];
                        var url = Object.keys(downloads)[0];
                        console.log(downloads[url]);

                        var hashes = new Array();

                        for (k in Object.keys(downloads[url])) {
                            var hash = Object.keys(downloads[url]);
                            console.log(hash[k]);
                            console.log(hash);
                            hashes.push({"hash": hash[k], "peers": downloads[url][hash[k]]});
                        }
                        var selection = {
                            "network": network.network,
                            "url":  url,
                            "hashes": hashes,
                        };
                        this.set("selection", selection);
                    }
                } else if (type === "peer") {
//                    var row = $('#' + type + '-' + index);
                }
/*              console.log(c);
                var c = row.children();
                console.log(c);
                c = c[c.length -1]; */
//               if ($('#' + type + '-' + index).css('visibility') === "hidden") {
//                   $('#' + type + '-' + index).css('visibility','')
//               } else {
//                   $('#' + type + '-' + index).css('visibility','hidden')
//               }
           },
            decrement: function(event, network, index){
                var download = this.get("downloads")[index];
                console.log(download);
            },
       });
    });
}

// This is /#users/<username>
// Should behave as a settings page for yourself but show your public revisions
// and user ID to others.
function userView(username, params){
    document.title = username + App.title;
    Ractive.load({
        userpage: 'userpage.tmpl',
    }).then(function(components){

        if (!App.Config.user) {
            location.hash = "login";
        }

        App.Views['userpage'] = new components.userpage({
            el: $('.main'),
            data: {profile: false},
            adaptor: ['Backbone'],
        });

        if (!$('.main').is(':visible')) {
            toggleMain();
        }

        // This function is pretty general in terms of populating tables
        function populate_table(table_type, url){
            // Grab the data
            $.get(url, function(data){
                // Update the DOM on success
                App.Views.userpage.set(table_type + "_paging_error", undefined);
                App.Views.userpage.set(table_type, data.data);
                App.Views.userpage[table_type] = data;

                // Show navigation links depending on the response data
                // This is where the jsonapi.org style of {links: {next: "http://"}}
                // comes in handy.
                if (data.links.hasOwnProperty("self")) {
                    var url = data.links.self.split('page=')[1];
                    if (url != undefined) {
                        if (url > 1) {
                            App.Views.userpage.set(table_type + "_back_available", true);
                        } else {
                            App.Views.userpage.set(table_type + "_back_available", false);
                        }
                    } 
                }

                if (data.links.hasOwnProperty("next")) {
                    App.Views.userpage.set(table_type + "_forward_available", true);
                }
            }).fail(function(){
               App.Views.userpage.set(table_type + "_paging_error", true);
            });
        }

        // Populate the user address line
        $.get('/v1/networks', function(data){
            if (data.data.length > 0){
                console.log(data.data);
                var network = data.data[0].name;
                var node_id = data.data[0].node_id;
                App.Views.userpage.set("network", network);
                App.Views.userpage.set("node_id", node_id);
                App.Views.userpage.set("uid", App.Config.user.uid);
            }
        });

        // Determine whether this is a profile or settings page.
        if (App.Config.user.username != username) {
//            populate_table("revisions", "/v1//user/" + username + "/revisions");
        } else {
            // Ugliest section in the file, but this stuff has to be somewhere
            App.Views.userpage.set("show_settings",     true);
            App.Views.userpage.set("sessions_button",   "Show");
            App.Views.userpage.set("revisions_button",  "Show");
            App.Views.userpage.set("friends_button",    "Show");
            App.Views.userpage.set("password_button",   "Show");
            App.Views.userpage.set("showing_sessions",  undefined);
            App.Views.userpage.set("showing_revisions", undefined);
            App.Views.userpage.set("showing_friends",   undefined);
            App.Views.userpage.set("showing_password",  undefined);

            populate_table("revisions", "/v1/users/" + username + "/revisions");
            populate_table("sessions",  "/v1/users/" + username + "/sessions");
        }

        App.Views.userpage.on({
            toggle:  function(event, section){
                var button = section + "_button"
                var showing = App.Views.userpage.get("showing_" + section);
                if (showing === undefined) {
                    App.Views.userpage.set(button, "Hide");
                    App.Views.userpage.set("showing_" + section, true);
                } else {
                    App.Views.userpage.set(button, "Show");
                    App.Views.userpage.set("showing_" + section, undefined);
                }
            },
            forward: function(event, table_type){
                var url = this[table_type].links.next;
                populate_table(table_type, url);
            },
            back:    function(event, table_type){
                var url = this[table_type].links.self.split('page=');
                var page = url[1] - 1;
                populate_table(table_type, url[0] + 'page=' + page);
            },
            select:  function(event, type, index){
                var row = $('#' + type + '-' + index);
                var c = row.children();
                c = c[c.length -1];
                if ($('#delete-' + type + '-' + index).css('visibility') === "hidden") {
                    c.style.visibility = "";
                } else {
                    c.style.visibility = "hidden";
                }
            },
            delete:  function(event, type, index){
                if        (type === "revision") {
                    var revision = this.get('revisions')[index];
                    console.log(revision);
                    $.ajax({
                        url:  '/v1/revisions/' + revision.hash,
                        type: "DELETE",
                        success: function(response){
                            // Remove the row on success.
                            $('#' + type + '-' + index).remove();
                        }
                    });
                } else if (type === "session") {
                    var session = this.get('sessions')[index];
                    $.ajax({
                        url:  '/v1/users/' + App.Config.user.username + '/sessions',
                        type: "DELETE",
                        data: {timestamp: session.created},
                        success: function(response){
                            // Remove the row on success.
                            $('#' + type + '-' + index).remove();
                        }
                    });
                  }
            },
            add_friend:      function(event){
                if (event.original.keyCode == 13){
                    event.original.preventDefault();
                    console.log(this.get("friend_addr"));
                }
            },
            change_password: function(event){
                event.original.preventDefault();
                var current = App.Views.userpage.get("pass0");
                var pass1   = App.Views.userpage.get("pass1");
                var pass2   = App.Views.userpage.get("pass2");
                // Bit of client-side validation.
                if (pass1 != pass2) {
                    App.Views.userpage.set("password_message", "Passwords were mismatched.");
               } else {
                   // Validate current password
                    $.ajax({
                        type:    "POST",
                        url:     "/v1/users/" + username,
                        data:    {verify_password: App.Views.userpage.get("pass0")},
                        success: function(data){
                            console.log(data);
                            if (data != true) {
                                App.Views.userpage.set("password_message", "Incorrect password.");
                            } else {
                                // POST new password
                                $.ajax({
                                    type: "POST",
                                    url:  "/v1/users/" + username,
                                    data: {password: App.Views.userpage.get("pass1")},
                                    success: function(data, success, jq_obj){
                                        if (jq_obj.status == 304){
                                            App.Views.userpage.set("password_message", "Passwords must be at least six characters.");
                                        } else {
                                            App.Views.userpage.set("password_message", "Password successfully changed.");
                                        }
                                    }
                                }).fail(function(){
                                    App.Views.userpave.set({password_message: "Couldn't contact the server."});
                                });
                            }
                        }
                    }).fail(function(){
                        App.Views.userpage.set({password_message: "Couldn't contact the server."});
                    });
               }
            }
        });
    });
}

Ractive.load({
    content:   'content.tmpl',
    synchrony: 'synchrony.tmpl',

}).then(function(components){

/*
    This is the content area of the page that holds external resources in an iframe
    it's loaded here so it can be displayed at all times alongside SPA templates.

*/    App.Views['content'] = new components.content({
        el: $('.content'),
        data: {events: App.stream},
        adaptor: ['Backbone'],
    });
/*
 * The current strategy revolves around subscribing to a channel named "public"
 * though this could just as well be a User UID to follow them through their
 * use of the proxy.
 *
 * DOM nodes are matched up to two parent nodes and changes are then reintegrated
 * where they're found to match. This strategy is not terribly effective /right now/
 * but is generally better than transmitting the entire document.
 *
 * The hardest fragment to match is a single character that's the only inhabitant of
 * its surrounding nodes.
 *
 * The protocol appears to want two major message types: "document" and "fragment"
 * where "document" is the entire tree and "fragment" is a subtree.
 *
 * This should be as simple as doing dom.patch(subtree)
 *
 */
    App.Views.content.socket = io.connect('/documents', {resource: "stream"})
    App.Views.content.socket.emit('subscribe', 'public')
    App.Views.content.socket.on("fragment", function(data){
        // Someone is sending us a document.
        console.log(data);
        parser = new DOMParser();
        doc = parser.parseFromString(data.document, "text/xml");
        // Clean out errors found by the parser.
        var element = doc.getElementsByTagName("parsererror");
        for (index = element.length - 1; index >= 0; index--) {
                element[index].parentNode.removeChild(element[index]);
        }
        console.log(doc);
        console.log(element);
        var doc_text = $(doc).text();
        console.log("doc_text: "+ doc_text);
//        window.doc = doc;
        var nodes = "";
        var text_data = "";
//        doc.children[0].className
        nodes = nodes + doc.children[0].nodeName
        if (doc.children[0].children) {
            nodes = nodes + ' ' + doc.children[0].children[0].nodeName
            if (doc.children[0].children[0].children) {
                nodes = nodes + ' ' + doc.children[0].children[0].children[0].nodeName
                text_data = doc.children[0].children[0].children[0].innerHTML
            } else {
                text_data = doc.children[0].children[0].innerHTML
            }
        } else {
            text_data = doc.children[0].innerHTML
        }
        console.log("nodes: " + nodes);
        console.log("text_data: " + text_data);
        var length = text_data.length;
        // First half
        var c = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(0,Math.ceil(length / 2)) + ')');
        var swapped = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(0,Math.ceil(length / 2)) + ')').first().html(data.document);
        console.log("swap attempt 1:");
        console.log(swapped.length);
        console.log(swapped.text());
        // Second half
        if (swapped.length != 1) {
            c.push.apply(c, $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(Math.ceil(length / 2), length) + ')'));
            var swapped = $('.iframe').contents().find(nodes + ':contains(' + text_data.slice(Math.ceil(length / 2), length) + ')').first().html(data.document);
            console.log("swap attempt 2:")
            console.log(swapped.length);
            console.log(swapped.text());
        }
        console.log("c: " + c.length);
        console.log(c);
        for (var i = 0; i < c.length; i++) {
            console.log($(c[i]).text());
        }
    });

//    Only transmit when textnode characters have been modified
    $('.iframe').contents().find('body').on('DOMCharacterDataModified', function(event){
//        Traverse to up to two parent elements and transmit the outerHTML.
        if (event.target.parentElement) {
            if (event.target.parentElement.parentElement) {
                edit_data = event.target.parentElement.parentElement.outerHTML;
            } else {
                edit_data = event.target.parentElement.outerHTML;
            }
        } else {
            edit_data = event.target.outerHTML;
        }
        
        App.Views.content.socket.emit('edit', edit_data);

        console.log(event);
        App.e = event;
    });

/*
    App.Views['results'] = new components.results({
        el: $('.results'),
        adaptor: ['Backbone'],
    });
    $('.results').hide();
    $('.results').click(function(){
        App.Views.search.set('term', '');
    });
*/
    // Search bar and an event handler for searching on input
    App.Views['synchrony'] = new components.synchrony({
        el: $('.synchrony'),
        data: {
        Config: App.Config,
        edit_button:"Edit",
        stream: App.stream,
        },
        adaptor: ['Backbone'],
    });

    App.Views.synchrony.socket = io.connect('/global', {resource:"stream"});
    App.Views.synchrony.socket.emit('join', "global");
    App.Views.synchrony.socket.on("message", function(data){
        App.stream.push(data.message);
        setTimeout(function(){ App.stream.pop(); }, 1000)
    });

    App.Views.synchrony.on({
        request: request, // Globally available request function

        edit: function(event){
            if ($('.edit_button').hasClass('active_button')) {
                $('.edit_button').removeClass('active_button');
            } else {
                $('.edit_button').addClass('active_button');
            }
            iframe = $('.iframe');
            var attr = iframe.contents().find('body').attr('contenteditable');
//            console.log(attr);
            if (typeof attr === typeof undefined || attr == false || attr == "false") {
                iframe.contents().find('body').attr('contenteditable','true');
                iframe.contents().find('body').attr('autocorrect','false');
                iframe.contents().find('body').attr('spellcheck','false');
                App.Views.synchrony.set('edit_button', "Done");
                $('.edit_button').html("Done");
           } else {
                iframe.contents().find('body').attr('contenteditable','false');
                App.Views.synchrony.set('edit_button', "Edit");
                $('.edit_button').html("Edit");
            }
        },
        settings:  function(event){
            window.location.hash = "#settings";
        },
        sessions:  function(event){
            window.location.hash = "#sessions";
        },
        show_hide: function(event){ // Show/hide the .main panel over content
            toggleMain();
        },
        chat:      function(event){
            window.location.hash = "#chat";
        },
        logout:    function(event){
            $.ajax({
                url:     "/v1/users/" + App.Config.user.username + "/sessions",
                type:    "DELETE",
                data:    {timestamp: App.Config.user.session.created},
                success: function(data){
                    window.location.hash = "#login";
                },
                error:   function(data){
                    console.log("error");
                    console.log(data);
                },
            });
        },
    });
});

function chatView() {
    document.title = "Chat" + App.title;
    Ractive.load({chat: 'chat.tmpl'}).then(function(components){
        App.Views['chat'] = new components.chat({
            el: $('.main'),
            data: {chat_available:true},
            adaptor: ['Backbone']
        });
        
        if (!App.Config.user) {
            location.hash = "login";
        }
        
        App.Views.chat.visible = false;

        // An array of messages typed into the input field.
        App.Views.chat.doskeys = [];
        App.Views.chat.current_doskey = 0;

        // Join the public channel and listen for messages
        App.Views.chat.socket = io.connect('/chat', {resource:"stream"});
        App.Views.chat.socket.emit('join', '#public');

        // Recieve chat messages.
        App.Views.chat.socket.on("privmsg", function(data){
            console.log(data);
//            if (!App.Views.sidebar.visible){ pulseSidebar(); }
//            The anonymous flag is for if you've permitted unsigned-up users to chat
//            via the auth server.
//            data = {m:message, u:username, a:anonymous_flag}
            $('.chat-messages').append('<br />&lt;' + linkUser(data.u) + '&gt; ' + data.m);
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
        });

        // Recieve the responses from commands
        App.Views.chat.socket.on("response", function(data){
            console.log(data);
//            if (!App.Views.chat.visible){ pulseChat(); }
            $('.chat-messages').append('<br />' + data.r);
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
        });

        // Server disappeared. TODO: Set a reconnect timer here.
//        App.Views.chat.socket.on("disconnect", function(data){
//            console.log(data);
//            App.Views.chat.set("chat_available", false);
//            App.Views.chat.set("chat_error", data.message);
//        });

        // We've connected to chat before authenticating and the
        // server is telling us to reconnect.
        App.Views.chat.socket.on("reconnect", function(data){
            $('.chat-messages').append('<br />Reconnecting...');
            $(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
            // Actually recreate the connection to re-auth.
            // Using chat.socket.disconnect and socket.connect doesn't work.
            App.Views.chat.socket.disconnect();
            delete App.Views.chat.socket;
            App.Views.chat.socket = io.connect('/chat', {resource:"stream"});
            console.log(data.m);
       });

        App.Views.chat.socket.on("appear_offline", function(data){
            $('[name="appear_offline"]').attr("checked", data);
        });

        if (App.Config.user){
            App.Views.chat.set("chat_available", true);
        }

    }).then(function(components){
        App.Views.chat.on({
            send: function(event){
                console.log("Sending");
            },

//            Transmit chat messages. this is an on-submit event.
            privmsg: function(event){
                event.original.preventDefault();
                var message = this.get("message");
    
                this.doskeys.push(message);
                App.Views.chat.current_doskey = 1;

                if (message){
                    if (message[0] === "/") {
                        App.Views.chat.socket.emit('cmd', message.substring(1));
                        console.log(this.get("message"));
                        $('#chat-input').val('');
                        this.set("message", '');
                    } else {
                        App.Views.chat.socket.emit('msg', message);
                        console.log(this.get("message"));
                        $('#chat-input').val('');
                        this.set("message", '');
                    }
                }
            },

            chat_appear_offline: function(event){
//                event.original.preventDefault();
                console.log(event);
                var appearing_offline = this.get("appearing_offline");
                console.log(appearing_offline)
                // We've prevented the default, so transmit the inverse,
                // as it's the state the user is aiming for
                if (appearing_offline){
                    App.Views.chat.socket.emit("appear_offline", 0);
                } else {
                    App.Views.chat.socket.emit("appear_offline", 1);
                }
            },

//            Implements a buffer of entered messages
//            available with the up and down arrow keys
//            Went with the name doskeys instead of buffer etc because it's more descriptive.
            doskeys: function(event){
                if (event.original.keyCode == 38){
                // If up arrow
                var current_line = this.get("message");
                    var doskeys = App.Views.chat.doskeys;
    
                    if (doskeys.length && App.Views.chat.current_doskey <= doskeys.length){
                        var line = App.Views.chat.doskeys[
                            App.Views.chat.doskeys.length - App.Views.chat.current_doskey
                        ];
                        this.set({message:line});
                        App.Views.chat.current_doskey += 1;
                    }

                } 
                else if (event.original.keyCode == 40){
                // If down arrow
                    var doskeys = App.Views.chat.doskeys;
                    if (doskeys.length && App.Views.chat.current_doskey != 1){
                        App.Views.chat.current_doskey -= 1;
                        var line = App.Views.chat.doskeys[
                            App.Views.chat.doskeys.length - App.Views.chat.current_doskey
                        ];
                        this.set({message:line});
                    }
                }
            },

            chat_settings: function(event){
                if ($('.chat-messages').is(':visible')) {
                    $('.chat-messages').hide();
                    $('.chat-settings-panel').show();
                } else {
                    $('.chat-settings-panel').hide();
                    $('.chat-messages').show();
                }
            },

        });
    });
    
}
function loginView() {
    document.title = "Log in or create an account" + App.title;
    Ractive.load({login: 'login.tmpl'}).then(function(components){
        App.Views['login'] = new components.login({
            el: $('.main'),
            adaptor: ['Backbone']
        });
    }).then(function(components){
        App.Views.login.on({
            login: function(event){

                event.original.preventDefault();

                var username = this.get("username0");
                var pass1 = this.get("pass0");
                App.Views.login.set("message", "Logging in...");
                // Use jQuery to make a PUT to /v1/users/:username/sessions
                $.ajax({
                    type: "PUT",
                    url: "/v1/users/" + username + "/sessions",
                    data: {password: pass1},
                    success: function(data, status){
                        // TODO: Reconnect to active sockets.
                        console.log(data);
                        console.log("Great success");
                        App.Config.user = data;
                        App.Views.synchrony.set("Config", App.Config);
                        location.hash = '';
                    },
                    error: function(data, status){
                        App.Views.login.set("message", "Incorrect username or password.");
                    }
                });

            },
            create: function(event){
                event.original.preventDefault();
                var username = this.get("username1");
                var pass1 = this.get("pass1");
                var pass2 = this.get("pass2");
                var email = this.get("email");
                if (pass1 != pass2 || pass1 == '') {
                    App.Views.login.set("message", "Passwords must match.");
                } else {
                    App.Views.login.set("message", "Give it a minute..");
                    $.ajax({
                        type: "PUT",
                        url: "/v1/users",
                        data: {
                            username: username,
                            password: pass1,
                            email: email
                        },
                        success: function(data, status){
                            console.log(data);
                            console.log("Great success");
                            App.Views.login.set("message", "Great success.");
                        },
                        error: function(data, status){
                            App.Views.login.set("message", "Server error.");
                        }
                    });
                }
            },
        });
    });
    
}

function accountPageGroups(){
    document.title = "Page groups" + App.title;
    console.log("System management.");
    Ractive.load({accountpagegroups: 'accountpagegroups.tmpl'}).then(function(components){
        App.Views['accountpagegroups'] = new components.accountpagegroups({
            el: $('.original'),
            adaptor: ['Backbone']
        });
    });
    
}

function settingsView() {
    document.title = "Settings" + App.title;
    Ractive.load({settings: 'settings.tmpl'}).then(function(components){
        App.Views['settings'] = new components.settings({
            el: $('.main'),
            data: App.Config,
            adaptor: ['Backbone']
        });
    });
}
function sessionsView() {
    document.title = "Sessions" + App.title;
    Ractive.load({sessions: 'sessions.tmpl'}).then(function(components){
        App.Views['sessions'] = new components.sessions({
            el: $('.main'),
            data: App.Config,
            adaptor: ['Backbone']
        });
    });
}
function manageView() {
    document.title = "Site management" + App.title;
    console.log("System management.");
    Ractive.load({manage: 'manage.tmpl'}).then(function(components){
        App.Views['manage'] = new components.manage({
            el: $('.original'),
            adaptor: ['Backbone']
        });
    });
}

function managePages(){}
function managePageGroups(){}
function manageUsers(){
    document.title = "User management" + App.title;
    console.log("User management.");
    Ractive.load({manageusers: 'manage-users.tmpl'}).then(function(components){
        App.Views['manageusers'] = new components.manageusers({
            el: $('.original'),
            adaptor: ['Backbone']
        });
    }).then(function(components){
        console.log(App.Views);

        $.get('/v1/users', function(response){
            App.Views.manageusers.set({users:response});
        });
    });

}
