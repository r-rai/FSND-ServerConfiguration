#!/usr/bin/env python2.7

from flask import Flask, render_template, request, redirect, jsonify, url_for
from flask import make_response, flash
from flask_sqlalchemy import SQLAlchemy
from flask import session as login_session
from config import Config
from sqlalchemy import create_engine
from sqlalchemy.pool import SingletonThreadPool
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Catalogue, Item
from oauth2client.client import flow_from_clientsecrets, FlowExchangeError
import httplib2
import json
import requests
import random
import string
import os

CLIENT_ID = json.loads(
    open('/home/ubuntu/Secrets/client_secrets.json', 'r').read())['web']['client_id']

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = os.urandom(24)
db = SQLAlchemy(app)

engine = create_engine('sqlite:////home/ubuntu/DB/catalog.db',poolclass=SingletonThreadPool)
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('/home/ubuntu/Secrets/client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(
            json.dumps('Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output

    # DISCONNECT - Revoke a current user's token and reset their login_session


@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session['access_token']
    print 'In gdisconnect access token is %s', access_token
    print 'User name is: '
    print login_session['username']
    if access_token is None:
        print 'Access Token is None'
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' \
        % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/')
@app.route('/catalogue/')
def showCatalogue():
    """Show all Catalogues"""
    catalogues = session.query(Catalogue).all()
    return render_template('catalogue.html', catalogues=catalogues)


@app.route('/catalogue/new/', methods=['GET', 'POST'])
def newCatalogue():
    """Add new Catalogue"""
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newCatalogue = Catalogue(name=request.form['name'])
        session.add(newCatalogue)
        flash('New Catalogue %s Successfully Created' % newCatalogue.name)
        session.commit()
        return redirect(url_for('showCatalogue'))
    else:
        return render_template('catalogue_new.html')


@app.route('/catalogue/<int:catalogue_id>/edit/', methods=['GET', 'POST'])
def editCatalogue(catalogue_id):
    """Edit Catalogue"""
    if 'username' not in login_session:
        return redirect('/login')
    theCatalogue = session.query(Catalogue).filter_by(id=catalogue_id).one()
    if request.method == 'POST':
        if request.form['name']:
            theCatalogue.name = request.form['name']
            flash('Catalogue Successfully Updated %s' % theCatalogue.name)
            return redirect(url_for('showCatalogue'))
    else:
        return render_template('catalogue_edit.html', catalogue=theCatalogue)


@app.route('/catalogue/<int:catalogue_id>/delete/', methods=['GET', 'POST'])
def deleteCatalogue(catalogue_id):
    """Delete Catalogue"""
    if 'username' not in login_session:
        return redirect('/login')
    theCatalogue = session.query(Catalogue).filter_by(id=catalogue_id).one()
    if request.method == 'POST':
        session.delete(theCatalogue)
        flash('%s Successfully Deleted' % theCatalogue.name)
        session.commit()
        return redirect(url_for('showCatalogue', catalogue_id=catalogue_id))
    else:
        return render_template('catalogue_delete.html', catalogue=theCatalogue)


@app.route('/catalogue/<int:catalogue_id>/')
@app.route('/catalogue/<int:catalogue_id>/item/')
def showItem(catalogue_id):
    """Show all Items"""
    catalogue = session.query(Catalogue).filter_by(id=catalogue_id).one()
    items = session.query(Item).filter_by(
        catalogue_id=catalogue_id).all()
    return render_template('item.html', items=items, catalogue=catalogue)


@app.route('/catalogue/<int:catalogue_id>/item/new', methods=['GET', 'POST'])
def newItem(catalogue_id):
    """Add new Item"""
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newItem = Item(name=request.form['name'],
                       description=request.form['description'],
                       catalogue_id=catalogue_id)
        session.add(newItem)
        session.commit()
        flash('%s Successfully Created' % (newItem.name))
        return redirect(url_for('showItem', catalogue_id=catalogue_id))
    else:
        return render_template('item_new.html', catalogue_id=catalogue_id)

    return render_template('item_new.html', catalogue_id=catalogue_id)


@app.route('/catalogue/<int:catalogue_id>/item/<int:item_id>/edit',
           methods=['GET', 'POST'])
def editItem(catalogue_id, item_id):
    """Edit Item"""
    if 'username' not in login_session:
        return redirect('/login')
    theItem = session.query(Item).filter_by(id=item_id).one()
    if request.method == 'POST':
        if request.form['name']:
            theItem.name = request.form['name']
        if request.form['description']:
            theItem.description = request.form['description']
        session.add(theItem)
        session.commit()
        flash('%s Successfully Updated' % (theItem.name))
        return redirect(url_for('showItem', catalogue_id=catalogue_id))
    else:
        return render_template('item_edit.html',
                               catalogue_id=catalogue_id,
                               item_id=item_id,
                               item=theItem)


@app.route('/catalogue/<int:catalogue_id>/item/<int:item_id>/delete',
           methods=['GET', 'POST'])
def deleteItem(catalogue_id, item_id):
    """Delete Item"""
    if 'username' not in login_session:
        return redirect('/login')
    theItem = session.query(Item).filter_by(id=item_id).one()
    if request.method == 'POST':
        session.delete(theItem)
        session.commit()
        flash('%s Successfully Deleted' % (theItem.name))
        return redirect(url_for('showItem', catalogue_id=catalogue_id))
    else:
        return render_template('item_delete.html',
                               catalogue_id=catalogue_id,
                               item=theItem)


@app.route('/catalogue/JSON')
def cataloguesJSON():
    """Return JSON for all the catalogues"""
    catalogues = session.query(Catalogue).all()
    return jsonify(catalogues=[c.serialize for c in catalogues])


@app.route('/catalogue/<int:catalogue_id>/JSON')
def catalogueItemJSON(catalogue_id):
    """Return JSON of all the items for a catalogue"""
    catalogue = session.query(Catalogue).filter_by(id=catalogue_id).one()
    items = session.query(Item).filter_by(
        catalogue_id=catalogue_id).all()
    return jsonify(Items=[i.serialize for i in items])


@app.route('/catalogue/<int:catalogue_id>/item/<int:item_id>/JSON')
def itemJSON(catalogue_id, item_id):
    """Return JSON for an item"""
    item = session.query(Item).filter_by(id=item_id).one()
    return jsonify(item=item.serialize)


if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0')