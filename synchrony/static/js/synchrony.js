/* 
   Synchrony 0.0.1
   A soft-realtime collaborative hyperdocument editor.
   Copyright Luke Brooks 2015

TODO:

PUT /v1/users

PUT     /v1/users/:name/sessions
GET     /v1/users/:name/sessions
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
		Config: {},
		Views:  {},
		stream: [],
		title: " - Synchrony",
	}

	// Ask the server who we are.
	$.get("/v1/users?me=1", function(data, status){
		App.Config.user = data;
	});

//	var m = new moment();
//	if (m.hour() >= 20 || m.hour() <= 6){
		setTimeout(function(){
			$('.main').addClass("after-hours");
		}, 50);
//	}

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
		'request':             'requestindex',
		'request/:resource':   'requestpage',
		'history/:resource':   'resourcehistory',
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
//		'*default': 'renderError',
	},

//	Attributes -> functions in the environment
	index:              indexView,
	requestindex:       requestIndex,
	requestresource:    requestView,
	resourcehistory:    resourceHistory,
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

//	Any pre-post render behaviors
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
	App.stream.push( '<span class="global-message">' + statement + '</span>' );
	setTimeout(function(){ App.stream.pop(); }, 8000);
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


// Fetch the index documents in a paginated manner
function fetchIndex(view){
	App.indexDocuments = new App.Documents();
	App.indexDocuments.fetch({
		error: function(){
			renderError("Couldn't contact the page server.");
			return false;
		},
		success: function(){
			// Pages are fetched after the template is placed in the DOM
			console.log("Successfully fetched index pages.")
			console.log(App.indexDocuments);
			// loop through the links we're interested in showing in a table on the
			// front page to translate their raw timestamps into human readable dates.
			models = App.indexDocuments.models;
				var index = 1;
			var total = models.length;
//			var docs =  upDate(models.paginate(index, 5));
			
			for (var i = 0; i < models.length; i++){
				var ts = models[i].get('modified');
				App.indexDocuments.models[i].set('modified', timeStamp(ts));
			}

			// Calculate pagination boundaries
			App.indexDocuments.i = 1;
			App.indexDocuments.per_page = 15;
			App.indexDocuments.end = Math.floor(
				App.indexDocuments.models.length / App.indexDocuments.per_page
			);
			// Partition the documents
			var	docs = App.indexDocuments.paginate(
				App.indexDocuments.per_page,
				App.indexDocuments.i
			);
			console.log(docs);
			if (docs.attributes){docs = docs.toJSON();}
			App.indexDocuments.docs = docs;
/*
			App.indexDocuments.set({
				docs:docs,
				prev_available:false,
				next_available:false,
			});
*/
			console.log(App.indexDocuments);
			if (App.Views.index){
				App.Views.index.set({docs: docs});
			}
 		},
	});
}


// Start the Backbone URL hash monitor
new App.Router();
Backbone.history.start();

function requestIndex(page, params){
	document.title = "Document Index" + App.title;
	console.log("Wiki page init.")
	if (!App.indexDocuments) {
		App.indexDocuments = new App.Documents();
		App.indexDocuments.fetch({
			error: function(){
				renderError("Couldn't contact the page server.");
			},
			success: function(){
				// Pages are fetched after the template is placed in the DOM
				// Paginate them, loop through the links we're interested in to
				// translate their raw timestamps into human readable dates.
				models = App.indexDocuments.models;
				for (var i = 0; i < models.length; i++){
					var ts = models[i].get('modified');
					App.indexDocuments.models[i].set('modified', timeStamp(ts));
				}
	 		},
		});
	}
	Ractive.load({
		wikiindex: 'wikiindex.tmpl',
	}).then(function(components){
		App.doc = new App.Document({title:page});
		App.Views['wikipage'] = new components.wikiindex({
			el: $('.original'),
			data: App.indexDocuments,
			adaptor: ['Backbone'],
		});
	});
}

function indexView(){
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
        if (!$('.main').hasClass('main_background')){
		    $('.main').addClass("main_background");
        }

        $.get('/v1/revisions', function(data){
            console.log(data);
            App.Views.index.set("revisions", data.data);
        });


		App.Views.index.on({
			request: function(event){
    			if (event.original.keyCode == 13){
	    			event.original.preventDefault();

		    		var url = this.get("url");
    				if (url.indexOf("://") > -1){
    					 url = url.slice(url.indexOf("://")+3, url.length);
    				}
    				if ($('.main').is(':visible')) {
    					toggleMain();
	    			}
    				// Update the appearance of the URL bar
    				location.hash = "request/" + url;
    				$.ajax({
    					type: "GET",
    					url: "/v1/request/" + url,
    					success: function(data, status){
    						console.log(data);
    						iframe = $('.iframe');
    						iframe.contents().find('body').html(data.response);
    						App.document = data.response;
    						$('.external_resources').html(data.response);
    					},
    					error: function(data, status){
    						renderError(data.responseJSON.message);
    					}
    				});
    			}
			},
		});
	});
}

function requestView(page, params){
	/*
		This view initialises the editor found in Editor.js on edit.
		This view has a socket that for document edits and events for things such as updating the last_modified attr
		The Edit, Cancel, Save and Delete behaviors correspond to this controller right here.
		and keep it readable.
	*/
	document.title = page + App.title;

	console.log('Wiki page "' + page + '".');
	Ractive.load({
		wikipage: 'wikipage.tmpl',
	}).then(function(components){
		App.doc = new App.Document({title:page});
		// Attach the template to the page
		App.Views['wikipage'] = new components.wikipage({
			el: $('.original'),
			data: { page:page, user: App.Config.user },
			adaptor: ['Backbone'],
		});

		function createSocket(){
			// Subscribe to a socket pertaining to this view
			var socket = io.connect('/wiki', {resource:"stream"});
			socket.emit('subscribe', page);

			socket.on('document', function(data){
				renderTyping(linkUser(data.user) + ' is editing');
				socket.last_edit = data.document
//				Assume the user doesn't want to see edits being made until they've said so
				if (App.Views.wikipage.realtime) {
/*					The document is replaced whole.
					Ideally we would diff what we currently have with what's been received
					and edit the corresponding node directly.
*/
					$('.editor').html(data.document);
				}

			});
			return socket;
		}

		function recreateSocket(){
			var socket = createSocket();
			if (socket.socket.connected) {
				renderGlobal("Reconnecting");
				App.Views.wikipage.socket = socket;	
			}
		}

		App.Views.wikipage.socket = createSocket();

		App.Views.wikipage.socket.on('disconnect', function(){
			renderError("Lost connection to document stream");
			if (!App.Views.wikipage.socket.socket.connected) { 
				recreateSocket();
			}
		});

		function saveSuccess(model, response){
			renderGlobal("Saved");
			console.log(response);
			App.doc.new = false;
		}

		function saveError(model,response){
			if (response.responseJSON && response.responseJSON.message) { 
				renderError(response.responseJSON.message);
			} else {
				renderError("Couldn't save the document.");
			}
			console.log(response);
		}

		App.Views.wikipage.on({
			/* The edit button should launch an Editor object
               that handles network synchronisation
               The other buttons are concerned with nothing more complicated
               than ending the editor object or telling the server to delete the document.

               If localStorage is permitted and we don't have a page we're visiting, save it.
			*/

			edit: function(event){
				
				App.edit("editor");
				App.editor.on("keyup", function(){
					App.Views.wikipage.socket.emit('edit', $('.editor').html());
				});
				$('.pen-menu').on("click", function(){
					App.Views.wikipage.socket.emit('edit', $('.editor').html());
				});
				$('.editholder').hide();
				$('.buttonholder').show();
			},

			save: function(event){

				var content = App.export();
				console.log(content);
				App.doc.set('content', content);

				if (App.doc.new) {
					App.doc.set({title: App.doc.get('id')})
					App.doc.set('id','')
					App.doc.url = '/v1/pages';
					App.doc.save(undefined,{
						error:   saveError,
						success: saveSuccess
					});
				} else {
					App.doc.save(null, {
						type: 'POST',
						error: saveError,
						success: saveSuccess
					});
				}

				App.doc.fetch({error: function() {
					renderError("Couldn't contact document server.");
				}, success: function(){
					console.log("Viewing fresh document.")

					// Cache content as an attribute
					App.doc.content = App.doc.get('content');
					$('.editor').html(App.doc.content);
					console.log(App.doc);
					App.editor.destroy();
					App.doc.set('content', App.markdown.makeHtml(App.doc.content));
					App.Views.wikipage.set({doc: App.doc});
					App.Views.sidebar.set({doc: App.doc});
					$('.editholder').show();
					$('.buttonholder').hide();
				}});
			},

			cancel: function(event){
//				Replace with original doc
				$('.editor').html(
					App.markdown.makeHtml(App.doc.content)
				);
//				Tx a cancel event

				App.editor.destroy();
				$('.editholder').show();
				$('.buttonholder').hide();
			},

			del: function(event){
				$.ajax({
					url: '/v1/pages/' + page,
					type: 'DELETE',
					success: function(response) {
						location.hash = '';
						renderGlobal('Deleted ' + page + '.');
					},
					error: function(response) {
						location.hash = '';
						console.log(response)
						renderError('Error deleting ' + page);
					}
				});
				fetchIndex();
			},

			// This is called on keydown events in the rename box, revealed on mouseover-ing the document title
			title: function(event){
				if (event.original.keyCode == 13){
					event.original.preventDefault();
					var newTitle = this.get("title");
					// Begin rename
					var oldTitle = this.get("page");
					this.set('page', newTitle);
					// Send the request for rename to the document server
					$.ajax({
						type: "POST",
						url: "/v1/pages/" + oldTitle,
						data: {title: newTitle},
						success: function(data, status){
							App.doc.set({title:newTitle});
							location.hash = "#wiki/" + newTitle;
							var pageLink = linkPage(newTitle);
							var userLink = linkUser(App.Config.user.username);
							var msg =  userLink + ' renamed ' + oldTitle + ' to ' + pageLink;
							renderGlobal(msg);
						},
						error: function(data, status){
							renderError(data.responseJSON.message);
						}
					});



					// End rename
				}
			},

			// There's a callback in the wikipage template for a mouseover event on the title
			// when it's triggered, one of these is called and we flip the title into or out of an edit box.
			editing_title: function(event){
				if (App.Config.user){
					$(this.el).find('.document-title').hide();
					$(this.el).find('.rename-document').css({visibility:"visible",display:"initial"});
				}
			},
			not_editing_title: function(event){
				if (App.Config.user){
					$(this.el).find('.document-title').show();
					$(this.el).find('.rename-document').css({visibility:"hidden",display:"none"});
				}
			},

			realtime: function(event){
				if (!App.Views.wikipage.realtime) {
					if (App.Views.wikipage.socket.last_edit){
						$('.editor').html(App.Views.wikipage.socket.last_edit);
					} 
					App.Views.wikipage.realtime = true;
					$('#realtime-button').html('Stop');
				} else {
					App.Views.wikipage.realtime = false;
					$('#realtime-button').html('Realtime');
				}
			},
		});
/*
		App.Views.wikipage.observe('title', function(title){
			console.log(title);
		});
*/

		// Load the actual document from the server.
		// Parse the url hash for revision id to define the request url
		// we'll be using on the document server.
		console.log(page);

		function fetchSuccess() {
			doc.new = false;
			doc.content = doc.get('content');
			doc.set('content', App.markdown.makeHtml(doc.content))
			var ts = doc.get('modified')
			doc.set('modified', timeStamp(ts));
			App.Views.wikipage.set({doc: App.doc});
			App.Views.sidebar.set("tab", {wikipage: true});
			App.Views.sidebar.set({doc: App.doc});
			// Mock up a new user object where instances have the doc available
			
			var newUser = App.Config.user;
			newUser.doc = App.doc
			App.Views.sidebar.set({user: newUser});
			// Normalise formatting between render/edit
			App.edit();
			App.editor.destroy();
		}
		function fetchError() {
			doc.new = true;
			$(".editor").html("New document.");
		}

		var doc = new App.Document({id: page});
		// If there's parameters in the url, IE a revision hash, tell Backbone
		if (!params){
			doc.fetch({ success: fetchSuccess, error: fetchError});
		} else {
			doc.fetch({ data: $.param(params), success: fetchSuccess, error: fetchError});
		}
		App.doc = doc;

		// Replace <div> elements produced by the enter key in the editor
		// with <br /> tags.
		// Move this out to an editor module.
		$('div[contenteditable]').keydown(function(e) {
		    // trap the return key being pressed
		    if (e.keyCode === 13) {
		      // insert 2 br tags (if only one br tag is inserted the cursor won't go to the next line)
		      document.execCommand('insertHTML', false, '<br /><br />');
		      // prevent the default behaviour of return key pressed
		      return false;
		    }
		});
	});
}

// This view permits users to view the revision history of a document
function resourceHistory(page, params){
	document.title = "Revision history for " + page + App.title;
	console.log('Page history for "' + page + '".');
	Ractive.load({
		pagehistory: 'pagehistory.tmpl',
	}).then(function(components){

		App.banner.show();
		App.doc = new App.Document({title:page});
		App.Views['pagehistory'] = new components.pagehistory({
			el: $('.original'),
			data: { page:page, user: App.Config.user },
			adaptor: ['Backbone'],
		});

		var doc = new App.Document({id: page});
		App.doc = doc;
		doc.fetch({
			data: {history: 0},
			success: function(){
				hist = doc.get('history');
				if (hist){
					for (var i = 0; i < hist.length; i++){
						hist[i].title = page;
						var ts = hist[i].created;
						hist[i].created = timeStamp(ts);
						doc.get('history')[i] = hist[i]
					}
					doc.trigger("change");
					doc.trigger("change:history");
				}

				App.Views.pagehistory.current_page = 1;

				hist.reverse();
				App.Views.pagehistory.hist_cache = hist;
				App.Views.pagehistory.end = Math.floor(hist.length / 10);
				hist = paginate(hist, App.Views.pagehistory.current_page, 10);



				App.Views.pagehistory.set({prev_available:false, next_available: false});

				if (App.Views.pagehistory.end > App.Views.pagehistory.current_page){
					App.Views.pagehistory.set({next_available: true});
				}

				doc.set("history", hist);
				var ts = App.doc.get('modified');
				App.doc.set('modified', timeStamp(ts));
				var ts = App.doc.get('created');
				App.doc.set('created', timeStamp(ts));
				App.Views.pagehistory.set({doc: App.doc});
			},
			error: function() {
				renderError("Couldn't retrieve page history.");
			},
		});
		App.Views.pagehistory.on({
			next: function(){
				var doc = App.Views.pagehistory.get("doc");
				var hist = App.Views.pagehistory.hist_cache;
				App.Views.pagehistory.current_page += 1;
				var history = paginate(hist, App.Views.pagehistory.current_page, 10);
				if (App.Views.pagehistory.current_page >= App.Views.pagehistory.end){
					App.Views.pagehistory.set({next_available:false})
				}
				if (App.Views.pagehistory.current_page > 1){
					App.Views.pagehistory.set({prev_available:true})
				}
				doc.set("history", history);
				App.Views.pagehistory.set({doc: doc});
			},
			prev: function(){
				var doc = App.Views.pagehistory.get("doc");
				var hist = App.Views.pagehistory.hist_cache;
				App.Views.pagehistory.current_page -= 1;
				var history = paginate(hist, App.Views.pagehistory.current_page, 10);
				doc.set("history", history);
				App.Views.pagehistory.set({doc: doc});
				if (App.Views.pagehistory.current_page == 1){
					App.Views.pagehistory.set({prev_available:false})
				}
				if (App.Views.pagehistory.current_page < App.Views.pagehistory.end){
					App.Views.pagehistory.set({next_available:true})
				}
			}
		});

	});
}

function accountView() {
	document.title = "Your account" + App.title;
	Ractive.load({
		accountview: 'accountview.tmpl',
	}).then(function(components){
		App.Views['accountview'] = new components.accountview({
			el: $('.original'),
			data: {},
			adaptor: ['Backbone'],
		});
		App.Views.accountview.on({
			edit: function(event){ console.log("Edit button says hello");},
			show_delete: function(event, index) { 
				var row = $('#'+index);
				var c = row.children();
				c = c[c.length -1]
				c.style.visibility = "";
			},
			hide_delete: function(event, index) { 
				var row = $('#'+index);
				var c = row.children();
				c = c[c.length -1]
				c.style.visibility = "hidden";
			},
			delete_session: function(event, index) { 
				var sessions = App.Views.accountview.get("sessions");
				console.log(sessions[index]);
				$.ajax({
					url: '/v1/users/' + App.Config.user.username + '/sessions',
					type: 'DELETE',
					data: {timestamp: sessions[index].timestamp},
					success: function(result) {
						$('#'+index).remove();
						App.Views.accountview.set(
							"session_count",
							App.Views.accountview.get("session_count") - 1
						);
					}
				});
			},
			edit: function(event){
				$('.editholder').hide();
				$('.buttonholder').show();
				$('.editor').show();
				$('.bio').hide();
			},
			save: function(event){
				var content = $('.editor').html();
				$.ajax({
					type: "POST",
					url: "/v1/users/" + App.Config.user.username,
					data: {bio: content},
					success: function(data,status){
						if (data){
							renderGlobal("Saved");
							var bio = App.markdown.makeHtml(data.bio);
							App.Views.accountview.set({bio: bio});
						} else {
							renderError("There was a problem saving your bio");
						}
					},
					error: function(xhr, status) {
						console.log(xhr);
						console.log(status);
						renderError("Couldn't update your user profile");
					}
				});
				$('.buttonholder').hide();
				$('.editholder').show();
				$('.editor').hide();
				$('.bio').show();
			},
			cancel: function(event){
				$('.buttonholder').hide();
				$('.editholder').show();
				$('.editor').hide();
				$('.bio').show()
			},
		});

		$.get('/v1/users/' + App.Config.user.username + '/sessions',
			function(data, status){
				console.log(data);
				for (var i = 0; i < data.sessions.length; i++){
					var ts = data.sessions[i].created;
					data.sessions[i].timestamp = ts
					data.sessions[i].created = timeStamp(ts);
					data.sessions[i].index = i;
				}
				App.Views.accountview.set({
					username: App.Config.user.username,
					sessions: data.sessions,
					session_count: data.session_count,
				});
		});
		$.get('/v1/users/' + App.Config.user.username + '?bio=1',
			function(data, status){
				console.log(data);
				data.mdbio = App.markdown.makeHtml(data.bio);
				App.Views.accountview.set({
					mdbio: data.mdbio,
					bio: data.bio,
				});
		});
	});
}

function logout(){
//	location = '/logout/';	
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
    });
}


// The profile page of a user
function userView(username, params){
	document.title = username + App.title;
	Ractive.load({
		userpage: 'userpage.tmpl',
	}).then(function(components){

		App.Views['userpage'] = new components.userpage({
			el: $('.main'),
			data: {profile: false},
			adaptor: ['Backbone'],
		});
        /*
        if (App.Config.user){
			$.get('/v1/users/' + username + '?profile=1', function(data, status){
				// Render the biography as a markdown document
				if (data.bio){ data.bio = App.markdown.makeHtml(data.bio); }
				App.Views.userpage.set({profile: data});
			}).fail(function(){
				App.Views.userpage.set({error:true})
			});

	    }
        */

        App.Views.userpage.on({
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

*/	App.Views['content'] = new components.content({
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
//		window.doc = doc;
		var nodes = "";
		var text_data = "";
//		doc.children[0].className
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

//	Only transmit when textnode characters have been modified
	$('.iframe').contents().find('body').on('DOMCharacterDataModified', function(event){
//		Traverse to up to two parent elements and transmit the outerHTML.
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
		request: function(event){
			if (event.original.keyCode == 13){
				event.original.preventDefault();

				var url = this.get("url");
				if (url.indexOf("://") > -1){
					 url = url.slice(url.indexOf("://")+3, url.length);
				}
				if ($('.main').is(':visible')) {
					toggleMain();
				}
				// Update the appearance of the URL bar
				location.hash = "request/" + url;
				$.ajax({
					type: "GET",
					url: "/v1/request/" + url,
					success: function(data, status, jq_obj){
						console.log(data);
                        //
                        // The Content-Hash and Overlay-Network headers are used
                        // to keep a log of what came from who, which can then
                        // be used in POST requests to /v1/revisions/downloads
                        //
                        console.log(jq_obj.getResponseHeader('Content-Hash'));
                        console.log(jq_obj.getResponseHeader('Overlay-Network'));
						iframe = $('.iframe');
						iframe.contents().find('body').html(data.response);
						App.document = data.response;
						$('.external_resources').html(data.response);
					},
					error: function(data, status){
						renderError(data.responseJSON.message);
					}
				});
			}
		},
		edit: function(event){
			iframe = $('.iframe');
			var attr = iframe.contents().find('body').attr('contenteditable');
//			console.log(attr);
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
		settings: function(event){
			window.location.hash = "#settings";
		},
		sessions: function(event){
			window.location.hash = "#sessions";
		},
		show_hide: function(event){ // Show/hide the .main panel over content
			toggleMain();
		},
		chat: function(event){
			window.location.hash = "#chat";
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
		App.Views.chat.visible = false;

		// An array of messages typed into the input field.
		App.Views.chat.doskeys = [];
		App.Views.chat.current_doskey = 0;

		// Join the public channel and listen for messages
		App.Views.chat.socket = io.connect('/chat', {resource:"stream"})
		App.Views.chat.socket.emit('join', 'public')

		// Recieve chat messages.
		App.Views.chat.socket.on("privmsg", function(data){
			console.log(data);
//			if (!App.Views.sidebar.visible){ pulseSidebar(); }
//			The anonymous flag is for if you've permitted unsigned-up users to chat
//			via the auth server.
//			data = {m:message, u:username, a:anonymous_flag}
			$('.chat-messages').append('<br />&lt;' + linkUser(data.u) + '&gt; ' + data.m);
			$(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
		});

		// Recieve the responses from commands
		App.Views.chat.socket.on("response", function(data){
			console.log(data);
//			if (!App.Views.chat.visible){ pulseChat(); }
			$('.chat-messages').append('<br />' + data.r);
			$(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
		});

		// Server disappeared. TODO: Set a reconnect timer here.
//		App.Views.chat.socket.on("disconnect", function(data){
//			console.log(data);
//			App.Views.chat.set("chat_available", false);
//			App.Views.chat.set("chat_error", data.message);
//		});

		// We've connected to chat before authenticating and the
		// server is telling us to reconnect.
		App.Views.chat.socket.on("reconnect", function(data){
			console.log(data.m);
			$('.chat-messages').append('<br />Reconnecting to chat...');
			$(".chat").animate({ scrollTop: $('.chat-messages').height() }, "slow");
			App.Views.chat.socket.disconnect();
			App.Views.chat.socket.socket.connect();
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

//			Transmit chat messages. this is an on-submit event.
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
//				event.original.preventDefault();
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

//			Implements a buffer of entered messages
//			available with the up and down arrow keys
//			Went with the name doskeys instead of buffer etc because it's more descriptive.
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
