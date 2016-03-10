// Extend Backbone.Router to support before: and after:
Backbone.Router.prototype.before = function () {};
Backbone.Router.prototype.after = function () {};

Backbone.Router.prototype.route = function (route, name, callback) {
  if (!_.isRegExp(route)) route = this._routeToRegExp(route);
  if (_.isFunction(name)) {
    callback = name;
    name = '';
  }
  if (!callback) callback = this[name];

  var router = this;

  Backbone.history.route(route, function(fragment) {
    var args = router._extractParameters(route, fragment);

    router.before.apply(router, arguments);
    callback && callback.apply(router, args);
    router.after.apply(router, arguments);

    router.trigger.apply(router, ['route:' + name].concat(args));
    router.trigger('route', name, args);
    Backbone.history.trigger('route', router, name, args);
  });
  return this;
};


// Mousenter and mouseleave extensions for Ractive.js
Ractive.events.mouseenter = function ( node, fire ) {
    node.addEventListener( 'mouseover', mouseoverHandler, false );
    
    return {
        teardown: function () {
            node.removeEventListener( 'mouseover', mouseoverHandler, false );
        }
    };
    
    function mouseoverHandler ( event ) {
        if ( !node.contains( event.relatedTarget ) ) {
            fire({ node: node, original: event });
        }
    }
};

Ractive.events.mouseleave = function ( node, fire ) {
    node.addEventListener( 'mouseout', mouseoutHandler, false );
    
    return {
        teardown: function () {
            node.removeEventListener( 'mouseout', mouseoutHandler, false );
        }
    };
    
    function mouseoutHandler ( event ) {
        if ( !node.contains( event.relatedTarget ) ) {
            fire({ node: node, original: event });
        }
    }
};

// Set cursor position
$.fn.setCursorPosition = function(pos) {
  this.each(function(index, elem) {
    if (elem.setSelectionRange) {
      elem.setSelectionRange(pos, pos);
    } else if (elem.createTextRange) {
      var range = elem.createTextRange();
      range.collapse(true);
      range.moveEnd('character', pos);
      range.moveStart('character', pos);
      range.select();
    }
  });
  return this;
};
